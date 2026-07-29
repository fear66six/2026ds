"""静态整景分析；每次调用只处理一张 Snapshot。"""

from __future__ import annotations

import time
from typing import Iterable

import cv2
import numpy as np

from . import config
from .calibration import PaperCalibration
from .edge_refinement import refine_polygon_from_contour
from .geometry import normalize_angle_deg, principal_angle_deg
from .models import PieceGeometry, PieceTaskStatus, SceneAnalysis, Snapshot, TemplateState
from .pieces import template_target_vertices_mm
from .puzzle_solver import TEMPLATE_IDS, assign_templates_global
from .vision import PaperFrame, cm_to_px, detect_divider_line, detect_paper, detect_pieces


def _edge_features(vertices: np.ndarray) -> tuple[list[float], list[float]]:
    pts = np.asarray(vertices, np.float64)
    edges = np.roll(pts, -1, axis=0) - pts
    lengths = np.linalg.norm(edges, axis=1)
    previous = -np.roll(edges, 1, axis=0)
    denom = np.linalg.norm(previous, axis=1) * np.maximum(lengths, 1e-9)
    cosines = np.clip(np.sum(previous * edges, axis=1) / np.maximum(denom, 1e-9), -1.0, 1.0)
    return lengths.tolist(), np.degrees(np.arccos(cosines)).tolist()


def _absolute_vertex_error(actual: np.ndarray, expected: np.ndarray) -> tuple[float, float]:
    """绝对放置误差：禁止再次自由配准，仅允许循环起点/方向对齐编号。"""
    actual = np.asarray(actual, dtype=np.float64).reshape(-1, 2)
    expected = np.asarray(expected, dtype=np.float64).reshape(-1, 2)
    if len(actual) != len(expected) or len(actual) == 0:
        return float("inf"), float("inf")
    best_max = float("inf")
    best_rms = float("inf")
    for candidate in (actual, actual[::-1]):
        for shift in range(len(candidate)):
            ordered = np.roll(candidate, shift, axis=0)
            errors = np.linalg.norm(ordered - expected, axis=1)
            max_err = float(np.max(errors))
            rms = float(np.sqrt(np.mean(errors**2)))
            if max_err < best_max:
                best_max = max_err
                best_rms = rms
    return best_max, best_rms


def _correction_from_absolute(actual: np.ndarray, expected: np.ndarray) -> tuple[float, np.ndarray]:
    """由绝对对应估计修正旋转/平移（用于报告，不用于判定配准）。"""
    actual = np.asarray(actual, dtype=np.float64).reshape(-1, 2)
    expected = np.asarray(expected, dtype=np.float64).reshape(-1, 2)
    if len(actual) != len(expected) or len(actual) == 0:
        return float("inf"), np.array([np.inf, np.inf])
    best = None
    for candidate in (actual, actual[::-1]):
        for shift in range(len(candidate)):
            ordered = np.roll(candidate, shift, axis=0)
            src_c = ordered.mean(axis=0)
            dst_c = expected.mean(axis=0)
            # 最小二乘旋转（禁止镜像）
            H = (ordered - src_c).T @ (expected - dst_c)
            u, _, vt = np.linalg.svd(H)
            r = vt.T @ u.T
            if np.linalg.det(r) < 0:
                vt = vt.copy()
                vt[-1, :] *= -1
                r = vt.T @ u.T
            angle = abs(normalize_angle_deg(float(np.degrees(np.arctan2(r[1, 0], r[0, 0])))))
            translation = dst_c - src_c
            score = float(np.max(np.linalg.norm(ordered - expected, axis=1)))
            if best is None or score < best[0]:
                best = (score, angle, translation)
    assert best is not None
    return float(best[1]), np.asarray(best[2], dtype=np.float64)


def _roi_metrics(
    contour_px: np.ndarray,
    frame_shape: tuple[int, ...],
    *,
    region: str,
    divider_y_px: float,
) -> tuple[bool, float, str | None]:
    h, w = frame_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(mask, [contour_px.astype(np.int32)], -1, 1, -1)
    total = float(np.count_nonzero(mask))
    if total < 1:
        return True, 0.0, "EMPTY_CONTOUR"
    if region == "UPPER_SOURCE":
        roi = np.zeros_like(mask)
        roi[: max(1, int(divider_y_px)), :] = 1
    else:
        roi = np.zeros_like(mask)
        roi[min(h - 1, int(divider_y_px)) :, :] = 1
    inside = float(np.count_nonzero(mask & roi))
    inside_ratio = inside / total
    x, y, bw, bh = cv2.boundingRect(contour_px.astype(np.int32))
    margin = 2
    touches_a4 = x <= margin or y <= margin or x + bw >= w - margin or y + bh >= h - margin
    # 接触分区边界
    ys, xs = np.where(mask > 0)
    touches_divider = bool(np.any(np.abs(ys - divider_y_px) <= 1.5))
    crosses = bool(np.any(ys < divider_y_px) and np.any(ys > divider_y_px))
    if touches_a4:
        return True, inside_ratio, "TOUCHES_A4_BORDER"
    if crosses:
        return True, inside_ratio, "CROSSES_DIVIDER"
    if touches_divider:
        return True, inside_ratio, "TOUCHES_VALID_ROI_BORDER"
    if inside_ratio < config.MIN_INSIDE_RATIO:
        return True, inside_ratio, "INSIDE_RATIO_TOO_LOW"
    cy = float(ys.mean())
    if region == "UPPER_SOURCE" and cy >= divider_y_px:
        return True, inside_ratio, "CENTER_OUTSIDE_REGION"
    if region == "LOWER_TARGET" and cy < divider_y_px:
        return True, inside_ratio, "CENTER_OUTSIDE_REGION"
    return False, inside_ratio, None


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
        self.last_assignment = None

    def analyze(self, snapshot: Snapshot, cycle_index: int) -> SceneAnalysis:
        self.full_analysis_count += 1
        started = time.perf_counter()
        assignment_margin = None
        assignment_total_cost = None
        warnings: list[str] = []
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
            t = time.perf_counter()
            assignment = assign_templates_global(pieces, origin_mm=self.target_origin_mm)
            timings["template_match_ms"] = (time.perf_counter() - t) * 1000.0
            self.last_assignment = assignment
            assignment_margin = assignment.confidence_margin
            assignment_total_cost = assignment.total_cost
            if assignment.accepted:
                pieces = list(assignment.assignments.values())
            else:
                warnings.append(assignment.rejection_reason or "ASSIGNMENT_REJECTED")
                for piece in pieces:
                    piece.template_id = None
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
                pieces, paper_valid, timings, assignment = self._from_image(analysis_frame, forced_paper)
                timings["rectify_ms"] = (time.perf_counter() - rectified_started) * 1000.0
            else:
                pieces, paper_valid, timings, assignment = self._from_image(snapshot.frame)
            self.last_assignment = assignment
            if assignment is not None:
                assignment_margin = assignment.confidence_margin
                assignment_total_cost = assignment.total_cost
                if not assignment.accepted:
                    warnings.append(assignment.rejection_reason or "ASSIGNMENT_REJECTED")
        templates = self._classify_templates(pieces, cycle_index)
        placed = {key for key, value in templates.items() if value.status == PieceTaskStatus.PLACED_OK}
        remaining = set(TEMPLATE_IDS) - placed
        scene_valid = paper_valid and all(templates[key].detected_piece is not None for key in TEMPLATE_IDS)
        if self.last_assignment is not None and not self.last_assignment.accepted:
            scene_valid = False
        timings["postprocess_ms"] = max(
            0.0, (time.perf_counter() - started) * 1000.0 - sum(timings.values())
        )
        timings["total_analysis_ms"] = (time.perf_counter() - started) * 1000.0
        if not scene_valid and not warnings:
            warnings.append("场景未能一一确认P1/P2/P3/P4")
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
            assignment_margin=assignment_margin,
            assignment_total_cost=assignment_total_cost,
        )

    def _from_simulation(self, records: Iterable[dict]) -> list[PieceGeometry]:
        result = []
        for index, record in enumerate(records):
            vertices = np.asarray(record["vertices_mm"], np.float64)
            edges, angles = _edge_features(vertices)
            # 仿真轮廓加点噪声后做边拟合，保证 edge_fit_rmse 非固定占位
            contour = []
            for i, vertex in enumerate(vertices):
                nxt = vertices[(i + 1) % len(vertices)]
                for t in np.linspace(0.0, 1.0, 12, endpoint=False):
                    contour.append(vertex * (1 - t) + nxt * t)
            refined = refine_polygon_from_contour(np.asarray(contour), expected_sides=len(vertices))
            use_vertices = refined.refined_vertices_mm if refined.valid else vertices
            edges, angles = _edge_features(use_vertices)
            result.append(
                PieceGeometry(
                    detected_id=index,
                    template_id=record.get("template_id"),
                    contour_px=np.rint(use_vertices * 4.0).astype(np.int32).reshape(-1, 1, 2),
                    vertices_px=use_vertices * 4.0,
                    vertices_mm=use_vertices,
                    edge_lengths_mm=edges,
                    inner_angles_deg=angles,
                    center_mm=tuple(np.mean(use_vertices, axis=0)),
                    angle_deg=float(record.get("angle_deg", principal_angle_deg(use_vertices))),
                    area_mm2=float(abs(cv2.contourArea(use_vertices.astype(np.float32)))),
                    edge_fit_rmse_mm=float(refined.edge_fit_rmse_mm if refined.valid else 0.01),
                    template_match_score=float(record.get("match_score", 0.0)),
                    confidence=float(record.get("confidence", 1.0)),
                    region=record["region"],
                    touches_boundary=False,
                    rough_vertices_mm=refined.rough_vertices_mm if refined.valid else vertices,
                    max_edge_residual_mm=float(refined.max_edge_residual_mm if refined.valid else 0.0),
                    inside_ratio=1.0,
                )
            )
        return result

    def _from_image(
        self, frame: np.ndarray, paper_override: PaperFrame | None = None
    ) -> tuple[list[PieceGeometry], bool, dict[str, float], object]:
        timings: dict[str, float] = {}
        t = time.perf_counter()
        paper = paper_override or detect_paper(frame)
        timings["rectify_ms"] = (time.perf_counter() - t) * 1000.0
        if paper is None:
            return [], False, timings, None
        divider = detect_divider_line(frame, paper) or config.DIVIDER_Y_CM
        divider_y_px = float(divider * paper.px_per_cm)
        t = time.perf_counter()
        # 已标定俯视图：粗检测+高分辨精修；否则回退旧 HSV 通路
        if paper_override is not None:
            from .white_segmentation import coarse_to_fine_contours

            fine_contours = coarse_to_fine_contours(frame, scale=0.5, pad_px=14)
            detected = []
            for cnt in fine_contours:
                piece = None
                from .vision import _contour_to_piece

                piece = _contour_to_piece(cnt, paper, divider, frame.shape)
                if piece is not None:
                    detected.append(piece)
        else:
            detected = detect_pieces(frame, paper, divider, config.DEFAULT_HSV_RANGES, live=False)
        timings["segmentation_ms"] = (time.perf_counter() - t) * 1000.0
        t_edge = time.perf_counter()
        candidates: list[PieceGeometry] = []
        for index, piece in enumerate(detected):
            contour_cm = np.asarray(piece.contour, dtype=np.float64).reshape(-1, 2)
            # contour 是像素；转 mm
            # DetectedPiece.contour 为像素坐标
            contour_px = np.asarray(piece.contour, dtype=np.float64).reshape(-1, 2)
            # 批量 px->cm->mm
            from .vision import _px_to_cm

            contour_cm = np.array([_px_to_cm(p, paper) for p in contour_px], dtype=np.float64)
            contour_mm = contour_cm * 10.0
            expected_sides = 3 if len(piece.vertices_cm) == 3 else (4 if len(piece.vertices_cm) == 4 else None)
            refined = refine_polygon_from_contour(contour_mm, expected_sides=expected_sides)
            vertices_mm = refined.refined_vertices_mm if refined.valid else np.asarray(piece.vertices_cm) * 10.0
            vertices_px = np.asarray([cm_to_px(tuple(v / 10.0), paper) for v in vertices_mm], np.float64)
            region = "UPPER_SOURCE" if piece.in_upper_half else "LOWER_TARGET"
            touches, inside_ratio, reject = _roi_metrics(
                piece.contour.reshape(-1, 1, 2),
                frame.shape,
                region=region,
                divider_y_px=divider_y_px,
            )
            edges, angles = _edge_features(vertices_mm)
            candidates.append(
                PieceGeometry(
                    detected_id=index,
                    template_id=None,
                    contour_px=piece.contour,
                    vertices_px=vertices_px,
                    vertices_mm=vertices_mm,
                    edge_lengths_mm=edges,
                    inner_angles_deg=angles,
                    center_mm=(piece.center_cm[0] * 10.0, piece.center_cm[1] * 10.0),
                    angle_deg=float(principal_angle_deg(vertices_mm)),
                    area_mm2=float(abs(cv2.contourArea(vertices_mm.astype(np.float32)))),
                    edge_fit_rmse_mm=float(refined.edge_fit_rmse_mm if refined.valid else 999.0),
                    template_match_score=float("inf"),
                    confidence=0.0,
                    region=region,
                    touches_boundary=touches,
                    rough_vertices_mm=refined.rough_vertices_mm,
                    max_edge_residual_mm=float(refined.max_edge_residual_mm if refined.valid else 999.0),
                    inside_ratio=inside_ratio,
                    rejection_reason=reject if touches else (refined.rejection_reason if not refined.valid else None),
                )
            )
        timings["edge_refine_ms"] = (time.perf_counter() - t_edge) * 1000.0
        t = time.perf_counter()
        assignment = assign_templates_global(candidates, origin_mm=self.target_origin_mm)
        timings["template_match_ms"] = (time.perf_counter() - t) * 1000.0
        if assignment.accepted:
            pieces = list(assignment.assignments.values())
        else:
            pieces = candidates
        timings["contour_extract_ms"] = 0.0
        return pieces, True, timings, assignment

    def _classify_templates(self, pieces: list[PieceGeometry], cycle_index: int) -> dict[str, TemplateState]:
        by_template = {piece.template_id: piece for piece in pieces if piece.template_id in TEMPLATE_IDS}
        states: dict[str, TemplateState] = {}
        for index, template_id in enumerate(TEMPLATE_IDS):
            expected = template_target_vertices_mm(index, self.target_origin_mm)
            piece = by_template.get(template_id)
            if piece is None:
                states[template_id] = TemplateState(
                    template_id, PieceTaskStatus.MISSING, None, expected, None, None, None, cycle_index
                )
                continue
            expected_center = np.mean(expected, axis=0)
            center_error = float(np.linalg.norm(np.asarray(piece.center_mm) - expected_center))
            max_vertex_err, rms_vertex_err = _absolute_vertex_error(piece.vertices_mm, expected)
            corr_rot, corr_t = _correction_from_absolute(piece.vertices_mm, expected)
            angle_error = corr_rot
            if piece.region == "LOWER_TARGET":
                identity_ok = piece.template_id == template_id
                placed_ok = (
                    identity_ok
                    and max_vertex_err <= self.vertex_tolerance_mm
                    and center_error <= self.center_tolerance_mm
                    and abs(angle_error) <= self.angle_tolerance_deg
                )
                status = PieceTaskStatus.PLACED_OK if placed_ok else PieceTaskStatus.PLACED_OFFSET
            else:
                status = PieceTaskStatus.UNPLACED
            states[template_id] = TemplateState(
                template_id,
                status,
                piece,
                expected,
                center_error,
                angle_error,
                max_vertex_err,
                cycle_index,
                rms_vertex_error_mm=rms_vertex_err,
            )
        return states
