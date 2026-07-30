"""静态整景分析；每次调用只处理一张 Snapshot。"""

from __future__ import annotations

import time
from typing import Iterable

import cv2
import numpy as np

from . import config
from .edge_refinement import refine_polygon_from_contour
from .geometry import normalize_angle_deg, principal_angle_deg
from .models import PieceGeometry, PieceTaskStatus, SceneAnalysis, Snapshot, TemplateState
from .pieces import template_target_vertices_mm
from .puzzle_solver import TEMPLATE_IDS, assign_templates_global
from .vision import PaperFrame, cm_to_px, detect_divider_line, detect_paper


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
    paper: PaperFrame,
    region: str,
    divider_y_cm: float,
) -> tuple[bool, float, str | None]:
    h, w = frame_shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.drawContours(mask, [contour_px.astype(np.int32)], -1, 1, -1)
    total = float(np.count_nonzero(mask))
    if total < 1:
        return True, 0.0, "EMPTY_CONTOUR"

    # 分区在 A4 纸面坐标中定义。横放 A4 时，纸面 y 轴对应图像 x 轴；
    # 如果继续使用水平像素线，左侧源碎片会被误判为跨越分界线。
    y0_cm, y1_cm = (
        (0.0, divider_y_cm)
        if region == "UPPER_SOURCE"
        else (divider_y_cm, config.A4_HEIGHT_CM)
    )
    roi_corners = np.rint(
        [
            cm_to_px((0.0, y0_cm), paper),
            cm_to_px((config.A4_WIDTH_CM, y0_cm), paper),
            cm_to_px((config.A4_WIDTH_CM, y1_cm), paper),
            cm_to_px((0.0, y1_cm), paper),
        ]
    ).astype(np.int32)
    roi = np.zeros_like(mask)
    cv2.fillConvexPoly(roi, roi_corners, 1)
    inside = float(np.count_nonzero(mask & roi))
    inside_ratio = inside / total

    contour_points = np.asarray(contour_px, dtype=np.float64).reshape(-1, 2)
    paper_polygon = np.asarray(paper.corners_px, dtype=np.float32).reshape(-1, 1, 2)
    min_paper_distance = min(
        cv2.pointPolygonTest(paper_polygon, (float(x), float(y)), True)
        for x, y in contour_points
    )
    touches_a4 = min_paper_distance <= 2.0

    # 接触分区边界
    from .vision import _px_to_cm

    contour_cm = np.asarray([_px_to_cm(point, paper) for point in contour_points])
    paper_y = contour_cm[:, 1]
    divider_margin_cm = 2.0 / max(float(paper.px_per_cm), 1.0)
    touches_divider = bool(np.any(np.abs(paper_y - divider_y_cm) <= divider_margin_cm))
    crosses = bool(np.any(paper_y < divider_y_cm) and np.any(paper_y > divider_y_cm))
    if touches_a4:
        return True, inside_ratio, "TOUCHES_A4_BORDER"
    if crosses:
        return True, inside_ratio, "CROSSES_DIVIDER"
    if touches_divider:
        return True, inside_ratio, "TOUCHES_VALID_ROI_BORDER"
    if inside_ratio < config.MIN_INSIDE_RATIO:
        return True, inside_ratio, "INSIDE_RATIO_TOO_LOW"
    center_y_cm = float(np.mean(paper_y))
    if region == "UPPER_SOURCE" and center_y_cm >= divider_y_cm:
        return True, inside_ratio, "CENTER_OUTSIDE_REGION"
    if region == "LOWER_TARGET" and center_y_cm < divider_y_cm:
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
    ) -> None:
        self.target_origin_mm = target_origin_mm
        self.center_tolerance_mm = center_tolerance_mm
        self.angle_tolerance_deg = angle_tolerance_deg
        self.vertex_tolerance_mm = vertex_tolerance_mm
        self.full_analysis_count = 0
        self.last_assignment = None
        self.last_paper = None
        self.last_divider_y_cm = None

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
            # A4 corners come only from detect_paper on the live frame.
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
        self, frame: np.ndarray
    ) -> tuple[list[PieceGeometry], bool, dict[str, float], object]:
        timings: dict[str, float] = {}
        t = time.perf_counter()
        paper = detect_paper(frame)
        timings["rectify_ms"] = (time.perf_counter() - t) * 1000.0
        if paper is None:
            self.last_paper = None
            self.last_divider_y_cm = None
            return [], False, timings, None
        divider = detect_divider_line(frame, paper) or config.DIVIDER_Y_CM
        self.last_paper = paper
        self.last_divider_y_cm = float(divider)
        t = time.perf_counter()
        from .white_segmentation import coarse_to_fine_contours
        from .vision import _contour_to_piece

        fine_contours = coarse_to_fine_contours(frame, scale=0.5, pad_px=14)
        detected = []
        for cnt in fine_contours:
            piece = _contour_to_piece(cnt, paper, divider, frame.shape)
            if piece is not None:
                detected.append(piece)
        timings["segmentation_ms"] = (time.perf_counter() - t) * 1000.0
        t_edge = time.perf_counter()
        candidates: list[PieceGeometry] = []
        for index, piece in enumerate(detected):
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
                paper=paper,
                region=region,
                divider_y_cm=divider,
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
