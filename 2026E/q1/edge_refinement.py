"""精确边拟合：approxPolyDP 仅作粗顶点，最终顶点由直线交点重建。"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class FittedLine:
    point_mm: np.ndarray
    direction: np.ndarray
    rmse_mm: float
    max_residual_mm: float
    inlier_count: int
    total_count: int


@dataclass
class RefinedPolygon:
    rough_vertices_mm: np.ndarray
    refined_vertices_mm: np.ndarray
    fitted_lines: list[FittedLine]
    edge_fit_rmse_mm: float
    max_edge_residual_mm: float
    valid: bool
    rejection_reason: str | None


def _point_line_distance(points: np.ndarray, origin: np.ndarray, direction: np.ndarray) -> np.ndarray:
    direction = direction / max(float(np.linalg.norm(direction)), 1e-9)
    delta = points - origin
    proj = delta @ direction
    closest = origin + np.outer(proj, direction)
    return np.linalg.norm(points - closest, axis=1)


def _fit_line_robust(points: np.ndarray, mad_k: float = 2.5) -> FittedLine | None:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        return None
    vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).flatten()
    origin = np.array([x0, y0], dtype=np.float64)
    direction = np.array([vx, vy], dtype=np.float64)
    residuals = _point_line_distance(pts, origin, direction)
    med = float(np.median(residuals))
    mad = float(np.median(np.abs(residuals - med))) + 1e-6
    keep = residuals <= med + mad_k * mad
    if int(np.count_nonzero(keep)) < 2:
        keep = np.ones(len(pts), dtype=bool)
    inliers = pts[keep]
    vx, vy, x0, y0 = cv2.fitLine(inliers.astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).flatten()
    origin = np.array([x0, y0], dtype=np.float64)
    direction = np.array([vx, vy], dtype=np.float64)
    residuals = _point_line_distance(inliers, origin, direction)
    return FittedLine(
        point_mm=origin,
        direction=direction / max(float(np.linalg.norm(direction)), 1e-9),
        rmse_mm=float(np.sqrt(np.mean(residuals**2))),
        max_residual_mm=float(np.max(residuals)) if len(residuals) else 0.0,
        inlier_count=int(len(inliers)),
        total_count=int(len(pts)),
    )


def _line_intersection(a: FittedLine, b: FittedLine, max_distance_mm: float) -> np.ndarray | None:
    p = a.point_mm
    r = a.direction
    q = b.point_mm
    s = b.direction
    denom = float(r[0] * s[1] - r[1] * s[0])
    if abs(denom) < 1e-8:
        return None
    t = float((q[0] - p[0]) * s[1] - (q[1] - p[1]) * s[0]) / denom
    point = p + t * r
    if float(np.linalg.norm(point - a.point_mm)) > max_distance_mm and float(
        np.linalg.norm(point - b.point_mm)
    ) > max_distance_mm:
        # still accept if near enough to rough vertex later
        pass
    return point


def _assign_contour_to_edges(contour_mm: np.ndarray, rough: np.ndarray) -> list[np.ndarray]:
    pts = np.asarray(contour_mm, dtype=np.float64).reshape(-1, 2)
    n = len(rough)
    buckets: list[list[np.ndarray]] = [[] for _ in range(n)]
    for point in pts:
        best_i = 0
        best_d = float("inf")
        for i in range(n):
            a = rough[i]
            b = rough[(i + 1) % n]
            ab = b - a
            length = float(np.linalg.norm(ab))
            if length < 1e-9:
                continue
            t = float(np.clip(np.dot(point - a, ab) / (length**2), 0.0, 1.0))
            dist = float(np.linalg.norm(point - (a + t * ab)))
            if dist < best_d:
                best_d = dist
                best_i = i
        buckets[best_i].append(point)
    result = []
    for i, bucket in enumerate(buckets):
        if len(bucket) < 2:
            result.append(np.vstack([rough[i], rough[(i + 1) % n]]))
        else:
            result.append(np.asarray(bucket, dtype=np.float64))
    return result


def refine_polygon_from_contour(
    contour_mm: np.ndarray,
    *,
    expected_sides: int | None = None,
    max_vertex_jump_mm: float = 25.0,
) -> RefinedPolygon:
    pts = np.asarray(contour_mm, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return RefinedPolygon(
            rough_vertices_mm=np.zeros((0, 2)),
            refined_vertices_mm=np.zeros((0, 2)),
            fitted_lines=[],
            edge_fit_rmse_mm=float("inf"),
            max_edge_residual_mm=float("inf"),
            valid=False,
            rejection_reason="TOO_FEW_CONTOUR_POINTS",
        )
    peri = float(cv2.arcLength(pts.astype(np.float32), True))
    approx = cv2.approxPolyDP(pts.astype(np.float32), 0.02 * peri, True).reshape(-1, 2)
    if expected_sides is not None and len(approx) != expected_sides:
        approx2 = cv2.approxPolyDP(pts.astype(np.float32), 0.03 * peri, True).reshape(-1, 2)
        if len(approx2) == expected_sides:
            approx = approx2
    if len(approx) < 3:
        return RefinedPolygon(
            rough_vertices_mm=approx,
            refined_vertices_mm=approx,
            fitted_lines=[],
            edge_fit_rmse_mm=float("inf"),
            max_edge_residual_mm=float("inf"),
            valid=False,
            rejection_reason="APPROX_VERTEX_COUNT",
        )
    if expected_sides is not None and len(approx) != expected_sides:
        return RefinedPolygon(
            rough_vertices_mm=approx,
            refined_vertices_mm=approx,
            fitted_lines=[],
            edge_fit_rmse_mm=float("inf"),
            max_edge_residual_mm=float("inf"),
            valid=False,
            rejection_reason="SIDE_COUNT_MISMATCH",
        )

    edge_points = _assign_contour_to_edges(pts, approx)
    lines: list[FittedLine] = []
    for segment in edge_points:
        fitted = _fit_line_robust(segment)
        if fitted is None:
            return RefinedPolygon(
                rough_vertices_mm=approx,
                refined_vertices_mm=approx,
                fitted_lines=[],
                edge_fit_rmse_mm=float("inf"),
                max_edge_residual_mm=float("inf"),
                valid=False,
                rejection_reason="LINE_FIT_FAILED",
            )
        lines.append(fitted)

    refined = []
    for i in range(len(lines)):
        inter = _line_intersection(lines[i - 1], lines[i], max_vertex_jump_mm * 4)
        if inter is None:
            return RefinedPolygon(
                rough_vertices_mm=approx,
                refined_vertices_mm=approx,
                fitted_lines=lines,
                edge_fit_rmse_mm=float("inf"),
                max_edge_residual_mm=float("inf"),
                valid=False,
                rejection_reason="PARALLEL_EDGES",
            )
        if float(np.linalg.norm(inter - approx[i])) > max_vertex_jump_mm:
            return RefinedPolygon(
                rough_vertices_mm=approx,
                refined_vertices_mm=approx,
                fitted_lines=lines,
                edge_fit_rmse_mm=float(np.mean([line.rmse_mm for line in lines])),
                max_edge_residual_mm=float(max(line.max_residual_mm for line in lines)),
                valid=False,
                rejection_reason="VERTEX_JUMP_TOO_LARGE",
            )
        refined.append(inter)
    refined_arr = np.asarray(refined, dtype=np.float64)
    area = abs(cv2.contourArea(refined_arr.astype(np.float32)))
    if area < 1.0:
        return RefinedPolygon(
            rough_vertices_mm=approx,
            refined_vertices_mm=refined_arr,
            fitted_lines=lines,
            edge_fit_rmse_mm=float(np.mean([line.rmse_mm for line in lines])),
            max_edge_residual_mm=float(max(line.max_residual_mm for line in lines)),
            valid=False,
            rejection_reason="AREA_TOO_SMALL",
        )
    return RefinedPolygon(
        rough_vertices_mm=approx.astype(np.float64),
        refined_vertices_mm=refined_arr,
        fitted_lines=lines,
        edge_fit_rmse_mm=float(np.mean([line.rmse_mm for line in lines])),
        max_edge_residual_mm=float(max(line.max_residual_mm for line in lines)),
        valid=True,
        rejection_reason=None,
    )
