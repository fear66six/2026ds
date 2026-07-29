"""第二问测试图：从完整矩形裁切 3~5 边形并分散到上半区"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from . import config

Point = Tuple[float, float]

UPPER_X_MIN_CM = 2.0
UPPER_X_MAX_CM = 19.5
UPPER_Y_MIN_CM = 1.5
UPPER_Y_MAX_CM = 13.2
SCATTER_MIN_GAP_CM = 0.6


def _scale_pieces(
    pieces: List[List[Point]], w: float, h: float, base_w: float = 10.0, base_h: float = 6.0
) -> List[np.ndarray]:
    sx, sy = w / base_w, h / base_h
    return [np.array([[x * sx, y * sy] for x, y in pts], dtype=np.float64) for pts in pieces]


def _polygon_area(vertices: np.ndarray) -> float:
    pts = vertices.reshape(-1, 2)
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def _min_edge(vertices: np.ndarray) -> float:
    pts = vertices.reshape(-1, 2)
    n = len(pts)
    return min(float(np.linalg.norm(pts[(i + 1) % n] - pts[i])) for i in range(n))


def _tiling_complex3(w: float, h: float) -> List[np.ndarray]:
    pieces = [
        [(0, 0), (4, 0), (4, 6), (0, 6)],
        [(4, 0), (10, 0), (10, 6)],
        [(4, 0), (10, 6), (4, 6)],
    ]
    return _scale_pieces(pieces, w, h)


def _clip_polygon_by_line(
    vertices: np.ndarray, p0: np.ndarray, p1: np.ndarray, keep_left: bool
) -> Optional[np.ndarray]:
    pts = list(vertices.reshape(-1, 2))
    if len(pts) < 3:
        return None
    line_vec = p1 - p0
    result: List[np.ndarray] = []

    def inside(p: np.ndarray) -> bool:
        cross = line_vec[0] * (p[1] - p0[1]) - line_vec[1] * (p[0] - p0[0])
        return cross >= -1e-9 if keep_left else cross <= 1e-9

    def intersect(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        ab = b - a
        denom = line_vec[0] * ab[1] - line_vec[1] * ab[0]
        if abs(denom) < 1e-12:
            return a
        t = (line_vec[1] * (a[0] - p0[0]) - line_vec[0] * (a[1] - p0[1])) / denom
        t = float(np.clip(t, 0.0, 1.0))
        return a + t * ab

    prev = np.array(pts[-1])
    for curr in [np.array(p) for p in pts]:
        curr_in, prev_in = inside(curr), inside(prev)
        if curr_in:
            if not prev_in:
                result.append(intersect(prev, curr))
            result.append(curr)
        elif prev_in:
            result.append(intersect(prev, curr))
        prev = curr

    if len(result) < 3:
        return None
    return np.array(result, dtype=np.float64)


def _is_axis_aligned_rectangle(poly: np.ndarray, tol: float = 0.2) -> bool:
    if len(poly) != 4:
        return False
    xs = np.round(poly[:, 0] / tol) * tol
    ys = np.round(poly[:, 1] / tol) * tol
    return len(np.unique(xs)) == 2 and len(np.unique(ys)) == 2


def _is_irregular_piece(poly: np.ndarray) -> bool:
    n = len(poly.reshape(-1, 2))
    if n in (3, 5):
        return True
    return not _is_axis_aligned_rectangle(poly)


def _accept_split(
    parent: np.ndarray, left: np.ndarray, right: np.ndarray, min_edge: float
) -> bool:
    if len(left) > 5 or len(right) > 5:
        return False
    if _min_edge(left) < min_edge * 0.95 or _min_edge(right) < min_edge * 0.95:
        return False
    if _polygon_area(left) < config.MIN_PIECE_AREA_CM2 or _polygon_area(right) < config.MIN_PIECE_AREA_CM2:
        return False
    pa = _polygon_area(parent)
    if pa > 1e-6 and abs(_polygon_area(left) + _polygon_area(right) - pa) / pa > 0.04:
        return False
    return True


def _try_split_axis(
    vertices: np.ndarray, rng: np.random.Generator, min_edge: float
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    if not _is_axis_aligned_rectangle(vertices):
        return None
    xmin, ymin = vertices.min(axis=0)
    xmax, ymax = vertices.max(axis=0)
    bw, bh = xmax - xmin, ymax - ymin
    kinds: List[str] = []
    if bw >= min_edge * 2.5:
        kinds.append("v")
    if bh >= min_edge * 2.5:
        kinds.append("h")
    if not kinds:
        return None
    rng.shuffle(kinds)
    for kind in kinds:
        for _ in range(8):
            if kind == "v":
                x = float(rng.uniform(xmin + min_edge, xmax - min_edge))
                p0, p1 = np.array([x, ymin - 1]), np.array([x, ymax + 1])
                left = _clip_polygon_by_line(vertices, p0, p1, True)
                right = _clip_polygon_by_line(vertices, p0, p1, False)
            else:
                y = float(rng.uniform(ymin + min_edge, ymax - min_edge))
                p0, p1 = np.array([xmin - 1, y]), np.array([xmax + 1, y])
                left = _clip_polygon_by_line(vertices, p0, p1, keep_left=False)
                right = _clip_polygon_by_line(vertices, p0, p1, keep_left=True)
            if left is None or right is None:
                continue
            if _accept_split(vertices, left, right, min_edge):
                return left, right
    return None


def _try_split_diagonal(
    vertices: np.ndarray, rng: np.random.Generator, min_edge: float
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    xmin, ymin = vertices.min(axis=0)
    xmax, ymax = vertices.max(axis=0)
    bw, bh = xmax - xmin, ymax - ymin
    if bw < min_edge * 1.35 or bh < min_edge * 1.35:
        return None
    for _ in range(20):
        t = float(rng.uniform(0.18, 0.82))
        if rng.random() < 0.5:
            p0 = np.array([xmin, ymin + t * bh])
            p1 = np.array([xmax, ymin + (1 - t) * bh])
        else:
            p0 = np.array([xmin + t * bw, ymin])
            p1 = np.array([xmin + (1 - t) * bw, ymax])
        left = _clip_polygon_by_line(vertices, p0, p1, True)
        right = _clip_polygon_by_line(vertices, p0, p1, False)
        if left is None or right is None:
            continue
        if _accept_split(vertices, left, right, min_edge):
            return left, right
    return None


def _try_split_corner(
    vertices: np.ndarray, rng: np.random.Generator, min_edge: float
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """从一角切到对边，产生三角形 + 多边形（复杂度接近 test.png）"""
    pts = vertices.reshape(-1, 2)
    xmin, ymin = pts.min(axis=0)
    xmax, ymax = pts.max(axis=0)
    bw, bh = xmax - xmin, ymax - ymin
    if bw < min_edge * 1.4 or bh < min_edge * 1.4:
        return None
    corners = [
        np.array([xmin, ymin]),
        np.array([xmax, ymin]),
        np.array([xmax, ymax]),
        np.array([xmin, ymax]),
    ]
    for _ in range(18):
        p0 = corners[int(rng.integers(4))]
        mode = int(rng.integers(0, 2))
        if mode == 0:
            if bw < min_edge * 2.2:
                continue
            p1 = np.array(
                [float(rng.uniform(xmin + min_edge, xmax - min_edge)), ymax if p0[1] <= ymin + 1e-6 else ymin]
            )
        else:
            if bh < min_edge * 2.2:
                continue
            p1 = np.array(
                [xmax if p0[0] <= xmin + 1e-6 else xmin, float(rng.uniform(ymin + min_edge, ymax - min_edge))]
            )
        if float(np.linalg.norm(p1 - p0)) < min_edge * 1.2:
            continue
        left = _clip_polygon_by_line(vertices, p0, p1, True)
        right = _clip_polygon_by_line(vertices, p0, p1, False)
        if left is None or right is None:
            continue
        if _accept_split(vertices, left, right, min_edge):
            return left, right
    return None


def _try_split(
    vertices: np.ndarray,
    rng: np.random.Generator,
    min_edge: float,
    irregular_bias: float = 0.65,
) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    order = ["corner", "diagonal", "axis"]
    if rng.random() >= irregular_bias:
        order = ["axis", "diagonal", "corner"]
    rng.shuffle(order[1:])
    for kind in order:
        if kind == "corner":
            s = _try_split_corner(vertices, rng, min_edge)
        elif kind == "diagonal":
            s = _try_split_diagonal(vertices, rng, min_edge)
        else:
            s = _try_split_axis(vertices, rng, min_edge)
        if s is not None:
            return s
    return None


def _vertex_counts(pieces: List[np.ndarray]) -> List[int]:
    return [len(p.reshape(-1, 2)) for p in pieces]


def _complexity_score(pieces: List[np.ndarray], n: int) -> float:
    """越高越接近 fig2 级复杂度（三角/五边、面积差异大、非矩形）"""
    counts = _vertex_counts(pieces)
    areas = [_polygon_area(p) for p in pieces]
    n_tri = sum(1 for c in counts if c == 3)
    n_pent = sum(1 for c in counts if c == 5)
    n_irreg = sum(1 for p in pieces if _is_irregular_piece(p))
    mean_a = float(np.mean(areas)) if areas else 1.0
    area_spread = float(np.std(areas) / max(mean_a, 1e-6))
    score = n_tri * 2.5 + n_pent * 2.0 + n_irreg * 0.8 + area_spread * 2.0
    if n >= 3 and max(areas) > 1.8 * min(areas):
        score += 1.5
    return score


def _is_grid_like(pieces: List[np.ndarray], w: float, h: float) -> bool:
    """排除 zigzag 式四宫格对称拼板"""
    if len(pieces) != 4 or not all(len(p) == 4 for p in pieces):
        return False
    cx = w / 2.0
    cy = h / 2.0
    grid_hits = 0
    for p in pieces:
        for v in p:
            if abs(v[0] - cx) < 0.35 * w or abs(v[1] - cy) < 0.35 * h:
                grid_hits += 1
    return grid_hits >= 6


def _complex_enough(pieces: List[np.ndarray], n: int, w: float, h: float) -> bool:
    """复杂度接近 test.png：含三角/五边或不规则斜切，且片面积差异明显"""
    if _is_grid_like(pieces, w, h):
        return False
    counts = _vertex_counts(pieces)
    if any(c == 3 for c in counts) or any(c == 5 for c in counts):
        return True
    areas = [_polygon_area(p) for p in pieces]
    if not areas:
        return False
    ratio = max(areas) / max(min(areas), 1e-6)
    n_irreg = sum(1 for p in pieces if _is_irregular_piece(p))
    if n_irreg >= 2 and ratio >= 1.45:
        return True
    if n >= 3 and ratio >= 1.85 and n_irreg >= 1:
        return True
    return _complexity_score(pieces, n) >= 3.2


def _split_rect_random_diagonal(w: float, h: float, rng: np.random.Generator) -> List[np.ndarray]:
    """随机主斜切：每次起点不同，复杂度接近 fig2 但形状不固定"""
    rect = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)
    mode = int(rng.integers(0, 3))
    if mode == 0:
        p0 = np.array([float(rng.uniform(0.08 * w, 0.92 * w)), 0.0])
        p1 = np.array([float(rng.uniform(0.08 * w, 0.92 * w)), h])
    elif mode == 1:
        p0 = np.array([0.0, float(rng.uniform(0.08 * h, 0.92 * h))])
        p1 = np.array([w, float(rng.uniform(0.08 * h, 0.92 * h))])
    else:
        if rng.random() < 0.5:
            p0 = np.array([0.0, float(rng.uniform(0.05 * h, 0.95 * h))])
            p1 = np.array([w, float(rng.uniform(0.05 * h, 0.95 * h))])
        else:
            p0 = np.array([float(rng.uniform(0.05 * w, 0.95 * w)), 0.0])
            p1 = np.array([float(rng.uniform(0.05 * w, 0.95 * w)), h])
    left = _clip_polygon_by_line(rect, p0, p1, True)
    right = _clip_polygon_by_line(rect, p0, p1, False)
    if left is None or right is None or not _accept_split(rect, left, right, config.MIN_EDGE_CM):
        return [rect]
    return [left, right]


def _guillotine_tiling(w: float, h: float, n: int, rng: np.random.Generator) -> List[np.ndarray]:
    rect = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)
    pieces = [rect]
    attempts = 0
    while len(pieces) < n and attempts < 200:
        attempts += 1
        idx = int(rng.integers(len(pieces)))
        split = _try_split(pieces[idx], rng, config.MIN_EDGE_CM, irregular_bias=0.7)
        if split is None:
            continue
        a, b = split
        pieces = pieces[:idx] + [a, b] + pieces[idx + 1:]
    while len(pieces) > n:
        pieces.pop(int(rng.integers(len(pieces))))
    return pieces


def _guillotine_from_pieces(pieces: List[np.ndarray], n: int, rng: np.random.Generator) -> List[np.ndarray]:
    out = [p.copy() for p in pieces]
    attempts = 0
    while len(out) < n and attempts < 200:
        attempts += 1
        idx = int(rng.integers(len(out)))
        split = _try_split(out[idx], rng, config.MIN_EDGE_CM, irregular_bias=0.7)
        if split is None:
            continue
        a, b = split
        out = out[:idx] + [a, b] + out[idx + 1:]
    while len(out) > n:
        out.pop(int(rng.integers(len(out))))
    return out


def _inject_diagonal_cuts(pieces: List[np.ndarray], rng: np.random.Generator, n_cuts: int) -> List[np.ndarray]:
    out = [p.copy() for p in pieces]
    for _ in range(n_cuts):
        idxs = list(range(len(out)))
        rng.shuffle(idxs)
        done = False
        for idx in idxs:
            split = _try_split(out[idx], rng, config.MIN_EDGE_CM, irregular_bias=0.85)
            if split is None:
                continue
            a, b = split
            out = out[:idx] + [a, b] + out[idx + 1:]
            done = True
            break
        if not done:
            break
    return out


def _build_random_tiling(w: float, h: float, n: int, rng: np.random.Generator) -> List[np.ndarray]:
    # 随机主斜切起步 → 直切凑满 n 片 → 再随机加 1~3 刀斜切
    if rng.random() < 0.75:
        base = _split_rect_random_diagonal(w, h, rng)
    else:
        base = [np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)]
    pcs = _guillotine_from_pieces(base, n, rng)
    if len(pcs) != n:
        pcs = _guillotine_tiling(w, h, n, rng)
    if len(pcs) == n:
        n_cuts = int(rng.integers(1, 4 if n >= 3 else 2))
        pcs = _inject_diagonal_cuts(pcs, rng, n_cuts)
        while len(pcs) > n:
            pcs.pop(int(rng.integers(len(pcs))))
    return pcs


def get_tiling(w: float, h: float, n_pieces: int, rng: np.random.Generator) -> List[np.ndarray]:
    best: Optional[List[np.ndarray]] = None
    best_score = -1.0

    for _ in range(48):
        pcs = _build_random_tiling(w, h, n_pieces, rng)
        if len(pcs) != n_pieces or not _validate_tiling(pcs, w, h):
            continue
        score = _complexity_score(pcs, n_pieces)
        if score > best_score:
            best_score, best = score, pcs
        if _complex_enough(pcs, n_pieces, w, h):
            return pcs

    if best is not None and best_score >= 2.0:
        return best

    # 仍不满足：加强斜切后再试若干次（仍保持随机，不用固定模板）
    for _ in range(24):
        pcs = _guillotine_tiling(w, h, n_pieces, rng)
        if len(pcs) != n_pieces:
            continue
        pcs = _inject_diagonal_cuts(pcs, rng, int(rng.integers(2, 5)))
        while len(pcs) > n_pieces:
            pcs.pop(int(rng.integers(len(pcs))))
        if len(pcs) != n_pieces or not _validate_tiling(pcs, w, h):
            continue
        if _complex_enough(pcs, n_pieces, w, h):
            return pcs
        score = _complexity_score(pcs, n_pieces)
        if score > best_score:
            best_score, best = score, pcs

    if best is not None:
        return best
    pcs = _guillotine_tiling(w, h, n_pieces, rng)
    return pcs if len(pcs) == n_pieces else [np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float64)]


def _can_pack_in_upper_half(local_pieces: List[np.ndarray]) -> bool:
    try:
        order = sorted(range(len(local_pieces)), key=lambda i: -_polygon_area(local_pieces[i]))
        _pack_scatter_slots(local_pieces, order)
        return True
    except RuntimeError:
        return False


def _validate_tiling(pieces: List[np.ndarray], w: float, h: float) -> bool:
    total = sum(_polygon_area(p) for p in pieces)
    if abs(total - w * h) / (w * h) > 0.06:
        return False
    for p in pieces:
        if len(p) < 3 or len(p) > config.MAX_VERTICES:
            return False
        if _min_edge(p) < config.MIN_EDGE_CM * 0.9:
            return False
    return _can_pack_in_upper_half(pieces)


def _world_polygon(local_verts: np.ndarray, center_cm: Point, angle_deg: float) -> np.ndarray:
    c0 = local_verts.mean(axis=0)
    pts = np.asarray(local_verts, dtype=np.float64) - c0
    rad = np.deg2rad(angle_deg)
    cos_a, sin_a = np.cos(rad), np.sin(rad)
    rot = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    return pts @ rot.T + np.array(center_cm, dtype=np.float64)


def _polygons_overlap(a: np.ndarray, b: np.ndarray, gap_cm: float) -> bool:
    ax0, ay0 = float(a[:, 0].min()), float(a[:, 1].min())
    ax1, ay1 = float(a[:, 0].max()), float(a[:, 1].max())
    bx0, by0 = float(b[:, 0].min()), float(b[:, 1].min())
    bx1, by1 = float(b[:, 0].max()), float(b[:, 1].max())
    return not (ax1 + gap_cm < bx0 or bx1 + gap_cm < ax0 or ay1 + gap_cm < by0 or by1 + gap_cm < ay0)


def _fits_upper_half(poly: np.ndarray) -> bool:
    xmin, ymin = poly.min(axis=0)
    xmax, ymax = poly.max(axis=0)
    return (
        xmin >= UPPER_X_MIN_CM
        and ymin >= UPPER_Y_MIN_CM
        and xmax <= UPPER_X_MAX_CM
        and ymax <= UPPER_Y_MAX_CM
    )


def _piece_half_extents(local: np.ndarray, angle_deg: float = 0.0) -> Tuple[float, float]:
    probe = _world_polygon(local, (0.0, 0.0), angle_deg)
    hw = float(probe[:, 0].max() - probe[:, 0].min()) / 2.0
    hh = float(probe[:, 1].max() - probe[:, 1].min()) / 2.0
    return hw, hh


def _build_dynamic_slots(n: int, local_pieces: List[np.ndarray]) -> List[Tuple[Point, float]]:
    max_hw = max(_piece_half_extents(p, 0.0)[0] for p in local_pieces) + SCATTER_MIN_GAP_CM * 0.5
    max_hh = max(_piece_half_extents(p, 0.0)[1] for p in local_pieces) + SCATTER_MIN_GAP_CM * 0.5
    x_lo, x_hi = UPPER_X_MIN_CM + max_hw, UPPER_X_MAX_CM - max_hw
    y_lo, y_hi = UPPER_Y_MIN_CM + max_hh, UPPER_Y_MAX_CM - max_hh
    if x_lo >= x_hi or y_lo >= y_hi:
        raise RuntimeError("碎片尺寸过大，无法放入上半区")
    cols = 1 if n == 1 else 2
    rows = (n + cols - 1) // cols
    slots: List[Tuple[Point, float]] = []
    for i in range(n):
        col, row = i % cols, i // cols
        cx = x_lo + (col + 0.5) * (x_hi - x_lo) / cols
        cy = y_lo + (row + 0.5) * (y_hi - y_lo) / rows
        slots.append(((float(cx), float(cy)), 0.0))
    return slots


def _pack_scatter_slots(local_pieces: List[np.ndarray], order: List[int]) -> List[Tuple[Point, float]]:
    gap = SCATTER_MIN_GAP_CM
    slots: List[Tuple[Point, float]] = [((0.0, 0.0), 0.0)] * len(local_pieces)
    cursor_x, cursor_y, row_h = UPPER_X_MIN_CM + gap, UPPER_Y_MIN_CM + gap, 0.0
    for pi in order:
        local = local_pieces[pi]
        hw, hh = _piece_half_extents(local, 0.0)
        if cursor_x + hw > UPPER_X_MAX_CM - gap:
            cursor_x = UPPER_X_MIN_CM + gap
            cursor_y += row_h + gap
            row_h = 0.0
        if cursor_y + hh > UPPER_Y_MAX_CM - gap:
            raise RuntimeError("上半区空间不足")
        slots[pi] = ((float(cursor_x + hw), float(cursor_y + hh)), 0.0)
        cursor_x += 2.0 * hw + gap
        row_h = max(row_h, 2.0 * hh + gap)
    return slots


def compute_scatter_placements(
    local_pieces: List[np.ndarray], rng: np.random.Generator
) -> List[Tuple[Point, float]]:
    n = len(local_pieces)
    order = sorted(range(n), key=lambda i: -_polygon_area(local_pieces[i]))
    try:
        slots = _pack_scatter_slots(local_pieces, order)
    except RuntimeError:
        slots = _build_dynamic_slots(n, local_pieces)

    placed: List[np.ndarray] = []
    result: List[Optional[Tuple[Point, float]]] = [None] * n

    def try_place(local: np.ndarray, center: Point, ang: float) -> Optional[np.ndarray]:
        world = _world_polygon(local, center, ang)
        if not _fits_upper_half(world):
            return None
        if any(_polygons_overlap(world, prev, SCATTER_MIN_GAP_CM) for prev in placed):
            return None
        return world

    for pi in order:
        local = local_pieces[pi]
        slot_center, slot_ang = slots[pi]
        chosen: Optional[Tuple[Point, float]] = None
        for ang in (0.0, float(slot_ang), -8.0, 8.0, -15.0, 15.0, -22.0, 22.0):
            for jx, jy in ((0.0, 0.0), (0.2, 0.0), (-0.2, 0.0), (0.0, 0.2)):
                center = (slot_center[0] + jx, slot_center[1] + jy)
                world = try_place(local, center, ang)
                if world is not None:
                    chosen = (center, ang)
                    placed.append(world)
                    break
            if chosen:
                break
        if chosen is None:
            for ang in (0.0, -10.0, 10.0, -20.0, 20.0, -30.0, 30.0):
                hw, hh = _piece_half_extents(local, ang)
                x_lo, x_hi = UPPER_X_MIN_CM + hw + 0.15, UPPER_X_MAX_CM - hw - 0.15
                y_lo, y_hi = UPPER_Y_MIN_CM + hh + 0.15, UPPER_Y_MAX_CM - hh - 0.15
                if x_lo > x_hi or y_lo > y_hi:
                    continue
                for cx in np.linspace(x_lo, x_hi, 16):
                    for cy in np.linspace(y_lo, y_hi, 12):
                        world = try_place(local, (float(cx), float(cy)), ang)
                        if world is not None:
                            chosen = ((float(cx), float(cy)), ang)
                            placed.append(world)
                            break
                    if chosen:
                        break
                if chosen:
                    break
        if chosen is None:
            raise RuntimeError(f"无法在上半区为第 {pi + 1} 片找到无重叠位置")
        result[pi] = chosen
    return [result[i] for i in range(n)]


def _cm_to_px(pt_cm: Point, px_per_cm: float, margin_px: int = 40) -> Tuple[int, int]:
    return int(margin_px + pt_cm[0] * px_per_cm), int(margin_px + pt_cm[1] * px_per_cm)


def _px_to_cm_local(px: float, py: float, px_per_cm: float, margin: int) -> Tuple[float, float]:
    return (px - margin) / px_per_cm, (py - margin) / px_per_cm


def _scatter_piece_from_assembled(
    img: np.ndarray,
    assembled: np.ndarray,
    local_verts: np.ndarray,
    center_cm: Point,
    angle_deg: float,
    px_per_cm: float,
    margin: int,
) -> None:
    c0 = local_verts.mean(axis=0)
    pts_local = np.asarray(local_verts, dtype=np.float64) - c0
    rad = np.deg2rad(angle_deg)
    cos_a, sin_a = np.cos(rad), np.sin(rad)
    rot = np.array([[cos_a, -sin_a], [sin_a, cos_a]])

    dest_poly = (pts_local @ rot.T) + np.array(center_cm)
    dest_px = np.array([_cm_to_px((float(x), float(y)), px_per_cm, margin) for x, y in dest_poly], np.int32)
    mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [dest_px], 255)

    inv_rot = rot.T
    ah, aw = assembled.shape[:2]
    for y, x in zip(*np.where(mask > 0)):
        world_cm = _px_to_cm_local(float(x), float(y), px_per_cm, margin)
        local_cm = inv_rot @ (world_cm - np.array(center_cm)) + c0
        ax, ay = int(round(local_cm[0] * px_per_cm)), int(round(local_cm[1] * px_per_cm))
        if 0 <= ax < aw and 0 <= ay < ah:
            img[y, x] = assembled[ay, ax]
    cv2.polylines(img, [dest_px], True, (150, 150, 150), 1)


def generate_q2_scattered_image(
    width_cm: float = 10.0,
    height_cm: float = 6.0,
    n_pieces: int = 4,
    seed: int = 42,
    px_per_cm: float = 14.0,
) -> np.ndarray:
    w_px = int(config.A4_WIDTH_CM * px_per_cm + 80)
    h_px = int(config.A4_HEIGHT_CM * px_per_cm + 80)
    img = np.zeros((h_px, w_px, 3), dtype=np.uint8)
    margin = 40
    cv2.rectangle(img, (margin, margin), (w_px - margin, h_px - margin), (35, 35, 35), 1)
    div_y = margin + int(config.DIVIDER_Y_CM * px_per_cm)
    cv2.line(img, (margin, div_y), (w_px - margin, div_y), (255, 255, 255), 2)

    local_pieces: List[np.ndarray] = []
    placements: List[Tuple[Point, float]] = []
    for attempt in range(30):
        try_rng = np.random.default_rng(seed + attempt * 9973)
        try:
            local_pieces = get_tiling(width_cm, height_cm, n_pieces, try_rng)
            placements = compute_scatter_placements(local_pieces, try_rng)
            break
        except RuntimeError:
            continue
    else:
        raise RuntimeError("无法生成无重叠的随机测试图")

    aw = max(4, int(round(width_cm * px_per_cm)))
    ah = max(4, int(round(height_cm * px_per_cm)))
    assembled = np.full((ah, aw, 3), 255, dtype=np.uint8)
    cv2.rectangle(assembled, (0, 0), (aw - 1, ah - 1), (200, 200, 200), 1)

    for local, (center, angle) in zip(local_pieces, placements):
        _scatter_piece_from_assembled(img, assembled, local, center, angle, px_per_cm, margin)
    return img
