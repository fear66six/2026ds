"""静态整景分析；每次调用只处理一张 Snapshot。"""

from __future__ import annotations

import time
from typing import Iterable

import cv2
import numpy as np

from . import config
from .calibration import PaperCalibration
from .geometry import normalize_angle_deg, principal_angle_deg
from .models import PieceGeometry, PieceTaskStatus, SceneAnalysis, Snapshot, TemplateState
from .pieces import PIECE_TEMPLATES
from .puzzle_solver import assign_pieces
from .vision import PaperFrame, cm_to_px, detect_divider_line, detect_paper, detect_pieces


TEMPLATE_IDS = ("P1", "P2", "P3", "P4")


def _edge_features(vertices: np.ndarray) -> tuple[list[float], list[float]]:
    pts = np.asarray(vertices, np.float64)
    edges = np.roll(pts, -1, axis=0) - pts
    lengths = np.linalg.norm(edges, axis=1)
    previous = -np.roll(edges, 1, axis=0)
    denom = np.linalg.norm(previous, axis=1) * np.maximum(lengths, 1e-9)
    cosines = np.clip(np.sum(previous * edges, axis=1) / np.maximum(denom, 1e-9), -1.0, 1.0)
    return lengths.tolist(), np.degrees(np.arccos(cosines)).tolist()


def _cyclic_vertex_error(actual: np.ndarray, expected: np.ndarray) -> float:
    if len(actual) != len(expected) or len(actual) == 0:
        return float("inf")
    variants = []
    for candidate in (actual, actual[::-1]):
        for shift in range(len(candidate)):
            variants.append(float(np.max(np.linalg.norm(np.roll(candidate, shift, axis=0) - expected, axis=1))))
    return min(variants)


def _template_vertices_mm(index: int, origin_mm: tuple[float, float]) -> np.ndarray:
    return PIECE_TEMPLATES[index].world_vertices((origin_mm[0] / 10.0, origin_mm[1] / 10.0)) * 10.0


class SceneAnalyzer:
    def __init__(
        self,
        *,
        target_origin_mm: tuple[float, float] = (55.0, 168.5),
        center_tolerance_mm: float = 5.0,
        angle_tolerance_deg: float = 5.0,
        vertex_tolerance_mm: float = 8.0,
        paper_calibration: PaperCalibration | None = None,
    ) -> None:
        self.target_origin_mm = target_origin_mm
        self.center_tolerance_mm = center_tolerance_mm
        self.angle_tolerance_deg = angle_tolerance_deg
        self.vertex_tolerance_mm = vertex_tolerance_mm
        self.paper_calibration = paper_calibration
        self.full_analysis_count = 0

    def analyze(self, snapshot: Snapshot, cycle_index: int) -> SceneAnalysis:
        self.full_analysis_count += 1
        started = time.perf_counter()
        if "simulation_pieces" in snapshot.metadata:
            pieces = self._from_simulation(snapshot.metadata["simulation_pieces"])
            paper_valid = True
            timings = {
                "rectify_ms": 0.0,
                "segmentation_ms": 0.0,
                "contour_extract_ms": 0.0,
                "edge_refine_ms": 0.0,
                "template_match_ms": 0.0,
            }
        else:
            if self.paper_calibration is not None:
                rectified_started = time.perf_counter()
                analysis_frame = self.paper_calibration.rectify(snapshot.frame)
                output_w, output_h = self.paper_calibration.output_size
                forced_paper = PaperFrame(
                    corners_px=np.array(
                        [[0, 0], [output_w - 1, 0], [output_w - 1, output_h - 1], [0, output_h - 1]],
                        dtype=np.float32,
                    ),
                    px_per_cm=float((output_w / 21.0 + output_h / 29.7) / 2.0),
                    divider_y_cm=config.DIVIDER_Y_CM,
                )
                pieces, paper_valid, timings = self._from_image(analysis_frame, forced_paper)
                timings["rectify_ms"] = (time.perf_counter() - rectified_started) * 1000.0
            else:
                pieces, paper_valid, timings = self._from_image(snapshot.frame)
        templates = self._classify_templates(pieces, cycle_index)
        placed = {key for key, value in templates.items() if value.status == PieceTaskStatus.PLACED_OK}
        remaining = set(TEMPLATE_IDS) - placed
        scene_valid = paper_valid and all(templates[key].detected_piece is not None for key in TEMPLATE_IDS)
        timings["postprocess_ms"] = max(
            0.0, (time.perf_counter() - started) * 1000.0 - sum(timings.values())
        )
        timings["total_analysis_ms"] = (time.perf_counter() - started) * 1000.0
        warnings = [] if scene_valid else ["场景未能一一确认P1/P2/P3/P4"]
        return SceneAnalysis(
            cycle_index=cycle_index,
            image_path=snapshot.path,
            pieces=pieces,
            templates=templates,
            placed_templates=placed,
            remaining_templates=remaining,
            image_quality={
                "sharpness": snapshot.sharpness,
                "brightness": snapshot.brightness,
                "motion_score": snapshot.motion_score,
            },
            paper_valid=paper_valid,
            scene_valid=scene_valid,
            warnings=warnings,
            timings_ms=timings,
        )

    def _from_simulation(self, records: Iterable[dict]) -> list[PieceGeometry]:
        result = []
        for index, record in enumerate(records):
            vertices = np.asarray(record["vertices_mm"], np.float64)
            edges, angles = _edge_features(vertices)
            result.append(
                PieceGeometry(
                    detected_id=index,
                    template_id=record["template_id"],
                    contour_px=np.rint(vertices * 4.0).astype(np.int32).reshape(-1, 1, 2),
                    vertices_px=vertices * 4.0,
                    vertices_mm=vertices,
                    edge_lengths_mm=edges,
                    inner_angles_deg=angles,
                    center_mm=tuple(np.mean(vertices, axis=0)),
                    angle_deg=float(record.get("angle_deg", principal_angle_deg(vertices))),
                    area_mm2=float(abs(cv2.contourArea(vertices.astype(np.float32)))),
                    edge_fit_rmse_mm=0.0,
                    template_match_score=float(record.get("match_score", 0.0)),
                    confidence=float(record.get("confidence", 1.0)),
                    region=record["region"],
                    touches_boundary=False,
                )
            )
        return result

    def _from_image(
        self, frame: np.ndarray, paper_override: PaperFrame | None = None
    ) -> tuple[list[PieceGeometry], bool, dict[str, float]]:
        timings: dict[str, float] = {}
        t = time.perf_counter()
        paper = paper_override or detect_paper(frame)
        timings["rectify_ms"] = (time.perf_counter() - t) * 1000.0
        if paper is None:
            return [], False, timings
        divider = detect_divider_line(frame, paper) or config.DIVIDER_Y_CM
        t = time.perf_counter()
        detected = detect_pieces(frame, paper, divider, config.DEFAULT_HSV_RANGES, live=False)
        timings["segmentation_ms"] = (time.perf_counter() - t) * 1000.0
        t = time.perf_counter()
        assignments = assign_pieces(detected, (self.target_origin_mm[0] / 10.0, self.target_origin_mm[1] / 10.0))
        timings["template_match_ms"] = (time.perf_counter() - t) * 1000.0
        by_detected = {a.detected_index: a for a in assignments}
        t = time.perf_counter()
        result: list[PieceGeometry] = []
        for index, piece in enumerate(detected):
            assignment = by_detected.get(index)
            template_id = assignment.template_name.split("_", 1)[0] if assignment else None
            vertices_mm = np.asarray(piece.vertices_cm, np.float64) * 10.0
            vertices_px = np.asarray([cm_to_px(tuple(v), paper) for v in piece.vertices_cm], np.float64)
            edges, angles = _edge_features(vertices_mm)
            result.append(
                PieceGeometry(
                    detected_id=index,
                    template_id=template_id,
                    contour_px=piece.contour,
                    vertices_px=vertices_px,
                    vertices_mm=vertices_mm,
                    edge_lengths_mm=edges,
                    inner_angles_deg=angles,
                    center_mm=(piece.center_cm[0] * 10.0, piece.center_cm[1] * 10.0),
                    angle_deg=piece.angle_deg,
                    area_mm2=piece.area_cm2 * 100.0,
                    edge_fit_rmse_mm=0.0,
                    template_match_score=assignment.match_score if assignment else float("inf"),
                    confidence=max(0.0, 1.0 - (assignment.match_score / 20.0)) if assignment else 0.0,
                    region="UPPER_SOURCE" if piece.in_upper_half else "LOWER_TARGET",
                    touches_boundary=False,
                )
            )
        timings["contour_extract_ms"] = (time.perf_counter() - t) * 1000.0
        timings["edge_refine_ms"] = 0.0
        return result, True, timings

    def _classify_templates(self, pieces: list[PieceGeometry], cycle_index: int) -> dict[str, TemplateState]:
        by_template = {piece.template_id: piece for piece in pieces if piece.template_id in TEMPLATE_IDS}
        states: dict[str, TemplateState] = {}
        for index, template_id in enumerate(TEMPLATE_IDS):
            expected = _template_vertices_mm(index, self.target_origin_mm)
            piece = by_template.get(template_id)
            if piece is None:
                states[template_id] = TemplateState(
                    template_id, PieceTaskStatus.MISSING, None, expected, None, None, None, cycle_index
                )
                continue
            expected_center = np.mean(expected, axis=0)
            center_error = float(np.linalg.norm(np.asarray(piece.center_mm) - expected_center))
            angle_error = abs(normalize_angle_deg(piece.angle_deg))
            vertex_error = _cyclic_vertex_error(piece.vertices_mm, expected)
            if piece.region == "LOWER_TARGET":
                status = (
                    PieceTaskStatus.PLACED_OK
                    if center_error <= self.center_tolerance_mm
                    and angle_error <= self.angle_tolerance_deg
                    and vertex_error <= self.vertex_tolerance_mm
                    else PieceTaskStatus.PLACED_OFFSET
                )
            else:
                status = PieceTaskStatus.UNPLACED
            states[template_id] = TemplateState(
                template_id,
                status,
                piece,
                expected,
                center_error,
                angle_error,
                vertex_error,
                cycle_index,
            )
        return states
