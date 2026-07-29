"""几何工具：轮廓重采样、刚性变换（平移+旋转，禁止翻转）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

Point = Tuple[float, float]


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
