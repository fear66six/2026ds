"""几何工具：轮廓重采样、刚性变换（平移+旋转，禁止翻转）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Mapping, Tuple

import cv2
import numpy as np

Point = Tuple[float, float]


def apply_uniform_shared_edge_gap(
    vertices_by_id: Mapping[Hashable, np.ndarray],
    gap_mm: float,
    *,
    shared_edge_pairs: Iterable[
        tuple[Hashable, int, Hashable, int]
    ] | None = None,
    collinear_tolerance_mm: float = 0.5,
    minimum_shared_length_mm: float = 2.0,
) -> dict[Hashable, np.ndarray]:
    """Separate adjacent rigid polygons by a uniform normal gap."""

    polygons = {
        key: np.asarray(vertices, dtype=np.float64).reshape(-1, 2).copy()
        for key, vertices in vertices_by_id.items()
    }
    if float(gap_mm) <= 0.0 or len(polygons) < 2:
        return polygons

    piece_ids = list(polygons)
    piece_index_by_id = {
        piece_id: index for index, piece_id in enumerate(piece_ids)
    }
    constraints: list[tuple[int, int, np.ndarray, float]] = []
    if shared_edge_pairs is not None:
        seen_pairs: set[tuple[Hashable, int, Hashable, int]] = set()
        for first_id, first_edge_id, second_id, second_edge_id in shared_edge_pairs:
            if first_id not in polygons or second_id not in polygons:
                continue
            canonical = (first_id, first_edge_id, second_id, second_edge_id)
            reverse = (second_id, second_edge_id, first_id, first_edge_id)
            if canonical in seen_pairs or reverse in seen_pairs:
                continue
            seen_pairs.add(canonical)
            first = polygons[first_id]
            second = polygons[second_id]
            if not (0 <= first_edge_id < len(first)) or not (
                0 <= second_edge_id < len(second)
            ):
                continue
            first_start = first[first_edge_id]
            first_end = first[(first_edge_id + 1) % len(first)]
            second_start = second[second_edge_id]
            second_end = second[(second_edge_id + 1) % len(second)]
            first_tangent = first_end - first_start
            second_tangent = second_end - second_start
            first_length = float(np.linalg.norm(first_tangent))
            second_length = float(np.linalg.norm(second_tangent))
            if first_length <= 1e-9 or second_length <= 1e-9:
                continue
            first_tangent /= first_length
            second_tangent /= second_length
            if np.dot(first_tangent, second_tangent) < 0.0:
                second_tangent = -second_tangent
            tangent = first_tangent + second_tangent
            tangent_length = float(np.linalg.norm(tangent))
            tangent = (
                first_tangent if tangent_length <= 1e-9 else tangent / tangent_length
            )
            normal = np.array([-tangent[1], tangent[0]], dtype=np.float64)
            first_center = first.mean(axis=0)
            second_center = second.mean(axis=0)
            if np.dot(second_center - first_center, normal) < 0.0:
                normal = -normal
            first_midpoint = 0.5 * (first_start + first_end)
            second_midpoint = 0.5 * (second_start + second_end)
            existing_separation = float(
                np.dot(second_midpoint - first_midpoint, normal)
            )
            constraints.append(
                (
                    piece_index_by_id[first_id],
                    piece_index_by_id[second_id],
                    normal,
                    existing_separation,
                )
            )
    else:
        for first_index, first_id in enumerate(piece_ids):
            first = polygons[first_id]
            first_center = first.mean(axis=0)
            for second_index in range(first_index + 1, len(piece_ids)):
                second = polygons[piece_ids[second_index]]
                second_center = second.mean(axis=0)
                best: tuple[float, np.ndarray, float] | None = None
                for edge_index in range(len(first)):
                    start = first[edge_index]
                    end = first[(edge_index + 1) % len(first)]
                    edge = end - start
                    edge_length = float(np.linalg.norm(edge))
                    if edge_length <= 1e-9:
                        continue
                    tangent = edge / edge_length
                    for other_index in range(len(second)):
                        other_start = second[other_index]
                        other_end = second[(other_index + 1) % len(second)]
                        distances = (
                            abs(
                                tangent[0] * (other_start[1] - start[1])
                                - tangent[1] * (other_start[0] - start[0])
                            ),
                            abs(
                                tangent[0] * (other_end[1] - start[1])
                                - tangent[1] * (other_end[0] - start[0])
                            ),
                        )
                        if max(distances) > float(collinear_tolerance_mm):
                            continue
                        other_projection = sorted(
                            (
                                float(np.dot(other_start - start, tangent)),
                                float(np.dot(other_end - start, tangent)),
                            )
                        )
                        overlap = min(edge_length, other_projection[1]) - max(
                            0.0, other_projection[0]
                        )
                        if overlap < float(minimum_shared_length_mm):
                            continue
                        normal = np.array(
                            [-tangent[1], tangent[0]], dtype=np.float64
                        )
                        if np.dot(second_center - first_center, normal) < 0.0:
                            normal = -normal
                        existing_separation = float(
                            np.dot(other_start - start, normal)
                        )
                        candidate = (overlap, normal, existing_separation)
                        if best is None or candidate[0] > best[0]:
                            best = candidate
                if best is not None:
                    constraints.append(
                        (first_index, second_index, best[1], best[2])
                    )

    if not constraints and shared_edge_pairs is not None:
        raise ValueError("EDGE_GAP_SHARED_EDGES_MISSING")
    if not constraints:
        return polygons

    rows: list[np.ndarray] = []
    distances: list[float] = []
    for first_index, second_index, normal, existing_separation in constraints:
        row = np.zeros(2 * len(piece_ids), dtype=np.float64)
        row[2 * first_index : 2 * first_index + 2] = -normal
        row[2 * second_index : 2 * second_index + 2] = normal
        rows.append(row)
        distances.append(float(gap_mm) - existing_separation)

    for axis in range(2):
        row = np.zeros(2 * len(piece_ids), dtype=np.float64)
        row[axis::2] = 1.0
        rows.append(row)
        distances.append(0.0)

    translations = np.linalg.lstsq(
        np.asarray(rows),
        np.asarray(distances),
        rcond=None,
    )[0].reshape(len(piece_ids), 2)
    shifted = {
        piece_id: polygons[piece_id] + translations[index]
        for index, piece_id in enumerate(piece_ids)
    }

    original_points = np.vstack(list(polygons.values()))
    shifted_points = np.vstack(list(shifted.values()))
    original_center = 0.5 * (
        original_points.min(axis=0) + original_points.max(axis=0)
    )
    shifted_center = 0.5 * (
        shifted_points.min(axis=0) + shifted_points.max(axis=0)
    )
    center_delta = original_center - shifted_center
    return {
        piece_id: vertices + center_delta
        for piece_id, vertices in shifted.items()
    }


@dataclass
class RigidTransformResult:
    rotation_matrix: np.ndarray
    translation_mm: np.ndarray
    rotation_deg: float
    correspondence: list[int]
    source_vertices_mm: np.ndarray
    target_vertices_mm: np.ndarray
    transformed_vertices_mm: np.ndarray
    max_error_mm: float
    rms_error_mm: float
    determinant: float
    mirrored: bool
    valid: bool
    rejection_reason: str | None


def resample_polygon(vertices: np.ndarray, n: int = 64) -> np.ndarray:
    """按弧长均匀重采样闭合多边形"""
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return np.repeat(pts, n, axis=0)[:n]

    closed = np.vstack([pts, pts[0]])
    seg_lens = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    total = float(seg_lens.sum())
    if total < 1e-6:
        return np.repeat(pts[:1], n, axis=0)

    cum = np.concatenate([[0.0], np.cumsum(seg_lens)])
    samples = np.linspace(0.0, total, n, endpoint=False)
    out = []
    j = 0
    for s in samples:
        while j < len(seg_lens) - 1 and cum[j + 1] < s:
            j += 1
        seg_start = cum[j]
        seg_len = seg_lens[j]
        t = (s - seg_start) / seg_len if seg_len > 1e-9 else 0.0
        p = closed[j] * (1 - t) + closed[j + 1] * t
        out.append(p)
    return np.array(out, dtype=np.float64)


def polygon_centroid(vertices: np.ndarray) -> Tuple[float, float]:
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    return float(pts[:, 0].mean()), float(pts[:, 1].mean())


def polygon_maximum_clearance_point(
    vertices_mm: np.ndarray,
    resolution_mm: float = 0.25,
) -> np.ndarray:
    """Return the interior point farthest from the polygon boundary."""
    points = np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 2)
    if len(points) < 3:
        raise ValueError("polygon requires at least three vertices")

    minimum = points.min(axis=0)
    span = points.max(axis=0) - minimum
    padding = 4
    width = int(np.ceil(span[0] / resolution_mm)) + padding * 2 + 1
    height = int(np.ceil(span[1] / resolution_mm)) + padding * 2 + 1
    polygon_px = np.rint((points - minimum) / resolution_mm).astype(np.int32)
    polygon_px += padding

    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon_px.reshape(-1, 1, 2)], 255)
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    _, _, _, maximum_location = cv2.minMaxLoc(distance)
    location = np.asarray(maximum_location, dtype=np.float64) - padding
    return minimum + location * resolution_mm


def procrustes_rotation_no_flip(src0: np.ndarray, dst0: np.ndarray) -> np.ndarray:
    """
    计算最优旋转矩阵 R（det=+1，禁止镜像翻转），使 src0 @ R.T ≈ dst0。
    src0/dst0 均已去中心化。
    """
    H = src0.T @ dst0
    U, _, Vt = np.linalg.svd(H)
    R = Vt.T @ U.T
    if np.linalg.det(R) < 0:
        Vt = Vt.copy()
        Vt[-1, :] *= -1
        R = Vt.T @ U.T
    return R


def rotation_angle_deg(R: np.ndarray) -> float:
    return float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))


def _vertex_order_variants(vertices: np.ndarray, max_vertices: int = 8) -> list[np.ndarray]:
    """生成轮廓顶点的循环/逆序变体，消除 approxPolyDP 起点不一致"""
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    if n < 3 or n > max_vertices:
        return [pts]

    variants: list[np.ndarray] = []
    seen: set[tuple] = set()
    for k in range(n):
        for rev in (False, True):
            ordered = pts if not rev else pts[::-1]
            variant = np.roll(ordered, k, axis=0)
            key = tuple(map(tuple, np.round(variant, 4)))
            if key not in seen:
                seen.add(key)
                variants.append(variant)
    return variants


def _best_rigid_match(
    source_cm: np.ndarray,
    target_cm: np.ndarray,
    n: int = 64,
) -> Tuple[np.ndarray, float, float, np.ndarray]:
    """
    在禁止翻转的前提下，搜索最佳顶点对应关系并刚性对齐。
    返回 (对齐后顶点, 旋转角deg, 最大误差cm, 采用的源点采样)
    """
    src_raw = np.asarray(source_cm, dtype=np.float64).reshape(-1, 2)
    tgt_raw = np.asarray(target_cm, dtype=np.float64).reshape(-1, 2)
    use_raw = (
        len(src_raw) <= 8
        and len(tgt_raw) <= 8
        and len(src_raw) >= 3
        and len(src_raw) == len(tgt_raw)
    )

    if use_raw:
        dst = tgt_raw.copy()
    else:
        dst = resample_polygon(target_cm, n)

    dst_c = dst.mean(axis=0)
    best_aligned = dst.copy()
    best_src = dst.copy()
    best_angle = 0.0
    best_err = float("inf")

    for variant in _vertex_order_variants(source_cm):
        if use_raw:
            src_base = np.asarray(variant, dtype=np.float64).reshape(-1, 2)
        else:
            src_base = resample_polygon(variant, n)

        shifts = range(len(src_base)) if len(src_base) > 3 else range(1)
        for shift in shifts:
            src = np.roll(src_base, shift, axis=0) if shift else src_base
            src_c = src.mean(axis=0)
            R = procrustes_rotation_no_flip(src - src_c, dst - dst_c)
            angle = rotation_angle_deg(R)
            aligned = (src - src_c) @ R.T + dst_c
            err = float(np.linalg.norm(aligned - dst, axis=1).max())
            if err < best_err:
                best_err = err
                best_angle = angle
                best_aligned = aligned
                best_src = src.copy()

    return best_aligned, normalize_angle_deg(best_angle), best_err, best_src


def rigid_align_no_flip(source_cm: np.ndarray, target_cm: np.ndarray, n: int = 64) -> np.ndarray:
    """刚性对齐（仅平移+旋转，不翻转），返回对齐后的顶点"""
    aligned, _, _, _ = _best_rigid_match(source_cm, target_cm, n)
    return aligned


def apply_rigid_pose(
    local: np.ndarray,
    center: Tuple[float, float],
    angle_deg: float,
) -> np.ndarray:
    """将中心化形状做平面旋转+平移（不翻转）"""
    rad = np.deg2rad(angle_deg)
    c, s = np.cos(rad), np.sin(rad)
    R = np.array([[c, -s], [s, c]])
    cx, cy = center
    return local @ R.T + np.array([cx, cy])


def normalize_angle_deg(angle: float) -> float:
    """归一化到 [-180, 180]，取最短旋转方向"""
    return float(((angle + 180.0) % 360.0) - 180.0)


def principal_angle_deg(vertices_cm: np.ndarray) -> float:
    """形状主轴方向（度），用于估计平面旋转角"""
    pts = resample_polygon(vertices_cm, 32)
    pts = pts - pts.mean(axis=0)
    if float(np.max(np.abs(pts))) < 1e-6:
        return 0.0
    _, _, vt = np.linalg.svd(pts)
    v = vt[0]
    return normalize_angle_deg(float(np.degrees(np.arctan2(v[1], v[0]))))


def rotation_deg_source_to_target(source_cm: np.ndarray, target_cm: np.ndarray) -> float:
    """从 source 姿态旋转到 target 姿态所需角度（最短路径，不翻转）"""
    _, angle, _, _ = _best_rigid_match(source_cm, target_cm)
    return angle


def decompose_rigid_motion(
    source_cm: np.ndarray,
    target_cm: np.ndarray,
    n: int = 64,
) -> Tuple[np.ndarray, Tuple[float, float], Tuple[float, float], float]:
    """
    分解为：固定局部形状 + 起/止中心 + 终止旋转角（度）。
    局部形状取自最佳点对应的源轮廓采样。
    """
    aligned, end_angle, _, best_src = _best_rigid_match(source_cm, target_cm, n)
    start_c = np.array(polygon_centroid(best_src))
    local = best_src - start_c
    end_c = np.array(polygon_centroid(aligned))
    return local, (float(start_c[0]), float(start_c[1])), (float(end_c[0]), float(end_c[1])), end_angle


def interpolate_rigid_motion(
    source_cm: np.ndarray,
    target_cm: np.ndarray,
    t: float,
    n: int = 64,
) -> np.ndarray:
    """仿真用：形状不变，仅中心插值 + 角度插值（真实搬运效果）"""
    t = float(np.clip(t, 0.0, 1.0))
    local, start_c, end_c, end_angle = decompose_rigid_motion(source_cm, target_cm, n)
    center = (
        start_c[0] + t * (end_c[0] - start_c[0]),
        start_c[1] + t * (end_c[1] - start_c[1]),
    )
    return apply_rigid_pose(local, center, end_angle * t)


def interpolate_rigid_no_flip(
    source_cm: np.ndarray,
    target_cm: np.ndarray,
    t: float,
    n: int = 64,
) -> np.ndarray:
    """兼容旧接口，内部改为真实刚性搬运"""
    return interpolate_rigid_motion(source_cm, target_cm, t, n)


def compute_rigid_align_error(
    source_cm: np.ndarray,
    target_cm: np.ndarray,
    n: int = 64,
) -> Tuple[float, float]:
    """返回 (最大顶点误差cm, 旋转角度deg)，均为无翻转刚性对齐"""
    _, angle, max_err, _ = _best_rigid_match(source_cm, target_cm, n)
    return max_err, angle


def rigid_placement_transform(
    source_vertices: np.ndarray,
    target_vertices: np.ndarray,
    n: int = 64,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    """兼容旧接口：源质心、目标质心、旋转角。"""
    result = compute_rigid_transform(source_vertices, target_vertices, n=n)
    if not result.valid:
        _, start_c, end_c, end_angle = decompose_rigid_motion(source_vertices, target_vertices, n)
        return start_c, end_c, end_angle
    src_c = np.mean(result.source_vertices_mm, axis=0)
    dst_c = np.mean(result.target_vertices_mm, axis=0)
    return (float(src_c[0]), float(src_c[1])), (float(dst_c[0]), float(dst_c[1])), result.rotation_deg


def compute_rigid_transform(
    source_vertices_mm: np.ndarray,
    target_vertices_mm: np.ndarray,
    n: int = 64,
) -> RigidTransformResult:
    """求解 target ≈ R @ source + t，禁止镜像与缩放。"""
    src_raw = np.asarray(source_vertices_mm, dtype=np.float64).reshape(-1, 2)
    tgt_raw = np.asarray(target_vertices_mm, dtype=np.float64).reshape(-1, 2)
    if len(src_raw) < 3 or len(tgt_raw) < 3:
        return RigidTransformResult(
            np.eye(2),
            np.zeros(2),
            0.0,
            [],
            src_raw,
            tgt_raw,
            src_raw,
            float("inf"),
            float("inf"),
            1.0,
            False,
            False,
            "TOO_FEW_VERTICES",
        )

    use_raw = len(src_raw) == len(tgt_raw) and len(src_raw) <= 8
    dst = tgt_raw.copy() if use_raw else resample_polygon(tgt_raw, n)
    dst_c = dst.mean(axis=0)
    best = None
    for variant in _vertex_order_variants(src_raw):
        src_base = np.asarray(variant, dtype=np.float64) if use_raw else resample_polygon(variant, n)
        shifts = range(len(src_base)) if len(src_base) > 3 else range(1)
        for shift in shifts:
            src = np.roll(src_base, shift, axis=0) if shift else src_base
            src_c = src.mean(axis=0)
            R = procrustes_rotation_no_flip(src - src_c, dst - dst_c)
            det = float(np.linalg.det(R))
            if det <= 0:
                continue
            t = dst_c - R @ src_c
            transformed = (src @ R.T) + t
            # Kabsch with row vectors: (src-c) @ R.T + dst_c
            transformed = (src - src_c) @ R.T + dst_c
            t = dst_c - R @ src_c
            errors = np.linalg.norm(transformed - dst, axis=1)
            max_err = float(errors.max())
            rms = float(np.sqrt(np.mean(errors**2)))
            if best is None or max_err < best["max_err"]:
                best = {
                    "R": R,
                    "t": t,
                    "src": src,
                    "transformed": transformed,
                    "max_err": max_err,
                    "rms": rms,
                    "det": det,
                    "angle": normalize_angle_deg(rotation_angle_deg(R)),
                    "corr": list(range(len(src))),
                }
    if best is None:
        return RigidTransformResult(
            np.eye(2),
            np.zeros(2),
            0.0,
            [],
            src_raw,
            tgt_raw,
            src_raw,
            float("inf"),
            float("inf"),
            -1.0,
            True,
            False,
            "MIRRORED_OR_NO_SOLUTION",
        )
    return RigidTransformResult(
        rotation_matrix=best["R"],
        translation_mm=best["t"],
        rotation_deg=best["angle"],
        correspondence=best["corr"],
        source_vertices_mm=best["src"],
        target_vertices_mm=dst,
        transformed_vertices_mm=best["transformed"],
        max_error_mm=best["max_err"],
        rms_error_mm=best["rms"],
        determinant=best["det"],
        mirrored=False,
        valid=True,
        rejection_reason=None,
    )


def apply_rigid_transform(point_mm: np.ndarray, transform: RigidTransformResult) -> np.ndarray:
    point = np.asarray(point_mm, dtype=np.float64).reshape(2)
    return transform.rotation_matrix @ point + transform.translation_mm


def max_vertex_error(vertices_a: np.ndarray, vertices_b: np.ndarray, n: int = 64) -> float:
    a = resample_polygon(vertices_a, n)
    b = resample_polygon(vertices_b, n)
    return float(np.linalg.norm(a - b, axis=1).max())
