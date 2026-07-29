"""
第二问拼图求解：直角/边界种子 + 互补角回溯拼接（无 seed 依赖）

策略：
  1. 检测所有碎片，提取 ≤5 顶点多边形
  2. 种子候选：直角对齐目标四角，或任一边对齐目标矩形边界
  3. 从暴露边回溯搜索：边长匹配 + 内角互补
  4. 严格验证：顶点在框内、无重叠、覆盖率达标
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

import numpy as np

from .geometry import polygon_centroid, rigid_align_no_flip
from .assignment import PieceAssignment
from .vision import DetectedPiece

from . import config
from .piece import AnalyzedPiece
from .target import target_origin_for_size


@dataclass
class PlacedPiece:
    piece_idx: int
    vertices_cm: np.ndarray
    matched_edges: Set[int] = field(default_factory=set)


# ---------------------------------------------------------------------------
# 几何工具
# ---------------------------------------------------------------------------

def _interior_angle_deg(v_prev: np.ndarray, v_curr: np.ndarray, v_next: np.ndarray) -> float:
    e1 = v_prev - v_curr
    e2 = v_next - v_curr
    l1, l2 = float(np.linalg.norm(e1)), float(np.linalg.norm(e2))
    if l1 < 1e-9 or l2 < 1e-9:
        return 0.0
    cos_a = float(np.clip(np.dot(e1, e2) / (l1 * l2), -1.0, 1.0))
    return float(np.degrees(np.arccos(cos_a)))


def _right_angle_corners(vertices: np.ndarray, tol_deg: float = 22.0) -> List[int]:
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    return [
        i
        for i in range(n)
        if abs(_interior_angle_deg(pts[(i - 1) % n], pts[i], pts[(i + 1) % n]) - 90.0) <= tol_deg
    ]


def _rotate_translate(vertices: np.ndarray, angle_deg: float, translation: np.ndarray) -> np.ndarray:
    rad = np.deg2rad(angle_deg)
    c, s = np.cos(rad), np.sin(rad)
    R = np.array([[c, -s], [s, c]], dtype=np.float64)
    return vertices @ R.T + translation


def _align_edge_to_segment(
    vertices: np.ndarray,
    edge_idx: int,
    seg_a: np.ndarray,
    seg_b: np.ndarray,
    reverse: bool,
) -> Optional[np.ndarray]:
    n = len(vertices)
    e0 = vertices[edge_idx]
    e1 = vertices[(edge_idx + 1) % n]
    edge_vec = e1 - e0
    seg_vec = seg_b - seg_a
    if float(np.linalg.norm(edge_vec)) < 1e-6 or float(np.linalg.norm(seg_vec)) < 1e-6:
        return None

    ang_e = np.arctan2(edge_vec[1], edge_vec[0])
    ang_s = np.arctan2(seg_vec[1], seg_vec[0])
    if reverse:
        ang_e += np.pi
    theta_deg = float(np.degrees(ang_s - ang_e))

    rotated = _rotate_translate(vertices - e0, theta_deg, np.zeros(2))
    if reverse:
        anchor = rotated[(edge_idx + 1) % n]
        shift = seg_a - anchor
    else:
        anchor = rotated[edge_idx]
        shift = seg_a - anchor
    return rotated + shift


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    if n < 1e-9:
        return np.zeros(2)
    return v / n


def _align_right_angle_to_corner(
    vertices: np.ndarray,
    corner_idx: int,
    corner_xy: np.ndarray,
    dir_a: np.ndarray,
    dir_b: np.ndarray,
) -> Optional[np.ndarray]:
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2).copy()
    n = len(pts)
    v0 = pts[corner_idx]
    e_fwd = pts[(corner_idx + 1) % n] - v0
    e_back = pts[(corner_idx - 1) % n] - v0
    da = _unit(np.asarray(dir_a, dtype=np.float64))
    db = _unit(np.asarray(dir_b, dtype=np.float64))
    if float(np.linalg.norm(da)) < 1e-6 or float(np.linalg.norm(db)) < 1e-6:
        return None

    best: Optional[np.ndarray] = None
    best_score = float("inf")

    for e_first in (e_fwd, e_back):
        if float(np.linalg.norm(e_first)) < 1e-6:
            continue
        ang = np.arctan2(e_first[1], e_first[0])
        target_ang = np.arctan2(da[1], da[0])
        theta = float(np.degrees(target_ang - ang))
        rotated = _rotate_translate(pts - v0, theta, np.zeros(2))
        rc = rotated[corner_idx]
        rn = _unit(rotated[(corner_idx + 1) % n] - rc)
        rp = _unit(rotated[(corner_idx - 1) % n] - rc)

        for first_is_fwd in (True, False):
            r1, r2 = (rn, rp) if first_is_fwd else (rp, rn)
            ang_a = abs(float(np.degrees(np.arccos(np.clip(np.dot(r1, da), -1.0, 1.0)))))
            ang_b = abs(float(np.degrees(np.arccos(np.clip(np.dot(r2, db), -1.0, 1.0)))))
            sc = ang_a + ang_b
            if sc >= best_score:
                continue
            placed = rotated - rc + np.asarray(corner_xy, dtype=np.float64)
            if float(np.linalg.norm(placed[corner_idx] - corner_xy)) > 0.18:
                continue
            best_score = sc
            best = placed

    return best


def _align_edge_to_boundary(
    vertices: np.ndarray,
    edge_idx: int,
    side: str,
    ox: float,
    oy: float,
    w: float,
    h: float,
    slide: float,
) -> Optional[np.ndarray]:
    """
    将边对齐到目标矩形某条边界（首片种子）。
    side: top / bottom / left / right；slide 为沿边界滑动比例 [0,1]。
    """
    n = len(vertices)
    e0 = vertices[edge_idx]
    e1 = vertices[(edge_idx + 1) % n]
    el = float(np.linalg.norm(e1 - e0))
    if el < 1e-6:
        return None

    if side in ("top", "bottom") and el > w + 0.35:
        return None
    if side in ("left", "right") and el > h + 0.35:
        return None

    if side == "top":
        seg_a = np.array([ox + slide * max(w - el, 0.0), oy])
        seg_b = np.array([seg_a[0] + el, oy])
    elif side == "bottom":
        seg_a = np.array([ox + slide * max(w - el, 0.0), oy + h])
        seg_b = np.array([seg_a[0] + el, oy + h])
    elif side == "left":
        seg_a = np.array([ox, oy + slide * max(h - el, 0.0)])
        seg_b = np.array([ox, seg_a[1] + el])
    else:
        seg_a = np.array([ox + w, oy + slide * max(h - el, 0.0)])
        seg_b = np.array([ox + w, seg_a[1] + el])

    for reverse in (False, True):
        world = _align_edge_to_segment(vertices, edge_idx, seg_a, seg_b, reverse)
        if world is None:
            continue
        cx, cy = polygon_centroid(world)
        if not (ox - 0.1 <= cx <= ox + w + 0.1 and oy - 0.1 <= cy <= oy + h + 0.1):
            continue
        if side == "top" and cy < oy + 0.08:
            continue
        if side == "bottom" and cy > oy + h - 0.08:
            continue
        if side == "left" and cx < ox + 0.08:
            continue
        if side == "right" and cx > ox + w - 0.08:
            continue
        return world
    return None


def _target_corner_dirs(ox: float, oy: float, w: float, h: float) -> List[Tuple[np.ndarray, np.ndarray, np.ndarray]]:
    return [
        (np.array([ox, oy]), np.array([1.0, 0.0]), np.array([0.0, 1.0])),
        (np.array([ox + w, oy]), np.array([-1.0, 0.0]), np.array([0.0, 1.0])),
        (np.array([ox, oy + h]), np.array([1.0, 0.0]), np.array([0.0, -1.0])),
        (np.array([ox + w, oy + h]), np.array([-1.0, 0.0]), np.array([0.0, -1.0])),
    ]


def _select_seed(analyzed: List[AnalyzedPiece]) -> Optional[Tuple[int, int]]:
    best: Optional[Tuple[int, int]] = None
    best_area = -1.0
    for i, piece in enumerate(analyzed):
        corners = _right_angle_corners(piece.vertices_cm)
        if not corners:
            continue
        if piece.area_cm2 > best_area:
            best_area = piece.area_cm2
            best = (i, corners[0])
    return best


def _polygon_area(vertices: np.ndarray) -> float:
    pts = vertices.reshape(-1, 2)
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def _bbox(vertices: np.ndarray) -> Tuple[float, float, float, float]:
    pts = vertices.reshape(-1, 2)
    return float(pts[:, 0].min()), float(pts[:, 1].min()), float(pts[:, 0].max()), float(pts[:, 1].max())


def _point_in_poly(x: float, y: float, vertices: np.ndarray) -> bool:
    pts = vertices.reshape(-1, 2)
    n = len(pts)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def _overlap_area(a: np.ndarray, b: np.ndarray, grid: int = 24) -> float:
    ax0, ay0, ax1, ay1 = _bbox(a)
    bx0, by0, bx1, by1 = _bbox(b)
    x0, y0 = min(ax0, bx0), min(ay0, by0)
    x1, y1 = max(ax1, bx1), max(ay1, by1)
    if x1 - x0 < 0.1 or y1 - y0 < 0.1:
        return 0.0
    cell = ((x1 - x0) / grid) * ((y1 - y0) / grid)
    count = sum(
        1
        for x in np.linspace(x0, x1, grid)
        for y in np.linspace(y0, y1, grid)
        if _point_in_poly(x, y, a) and _point_in_poly(x, y, b)
    )
    return count * cell


def _any_overlap(placed: List[PlacedPiece], new_verts: np.ndarray) -> bool:
    return any(_overlap_area(p.vertices_cm, new_verts) > 0.04 for p in placed)


def _vertices_inside(vertices: np.ndarray, ox: float, oy: float, w: float, h: float, tol: float = 0.25) -> bool:
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    return bool(
        np.all(pts[:, 0] >= ox - tol)
        and np.all(pts[:, 0] <= ox + w + tol)
        and np.all(pts[:, 1] >= oy - tol)
        and np.all(pts[:, 1] <= oy + h + tol)
    )


def _centroid_inside(vertices: np.ndarray, ox: float, oy: float, w: float, h: float) -> bool:
    cx, cy = polygon_centroid(vertices)
    return ox - 0.15 <= cx <= ox + w + 0.15 and oy - 0.15 <= cy <= oy + h + 0.15


def _edge_on_boundary(p0, p1, ox, oy, w, h, tol=0.45) -> bool:
    mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
    if abs(my - oy) < tol and ox - tol <= mx <= ox + w + tol:
        return True
    if abs(my - (oy + h)) < tol and ox - tol <= mx <= ox + w + tol:
        return True
    if abs(mx - ox) < tol and oy - tol <= my <= oy + h + tol:
        return True
    if abs(mx - (ox + w)) < tol and oy - tol <= my <= oy + h + tol:
        return True
    return False


def _piece_has_boundary_edge(vertices: np.ndarray, ox: float, oy: float, w: float, h: float) -> bool:
    pts = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    return any(_edge_on_boundary(pts[i], pts[(i + 1) % n], ox, oy, w, h) for i in range(n))


def _exposed_edges(placed: List[PlacedPiece]) -> List[Tuple[int, int, np.ndarray, np.ndarray]]:
    out = []
    for pi, pp in enumerate(placed):
        verts = pp.vertices_cm
        n = len(verts)
        for ei in range(n):
            if ei in pp.matched_edges:
                continue
            out.append((pi, ei, verts[ei].copy(), verts[(ei + 1) % n].copy()))
    return out


def _interior_angle_at(vertices: np.ndarray, vertex_idx: int) -> float:
    n = len(vertices)
    return _interior_angle_deg(
        vertices[(vertex_idx - 1) % n],
        vertices[vertex_idx],
        vertices[(vertex_idx + 1) % n],
    )


def _angle_complement_score(
    placed_verts: np.ndarray, placed_edge: int, new_verts: np.ndarray, new_edge: int, reverse: bool
) -> float:
    n1 = len(placed_verts)
    n2 = len(new_verts)
    va = placed_edge
    vb = (placed_edge + 1) % n1
    ang_a = _interior_angle_at(placed_verts, va)
    ang_b = _interior_angle_at(placed_verts, vb)

    if reverse:
        nu = (new_edge + 1) % n2
        nv = new_edge
    else:
        nu = new_edge
        nv = (new_edge + 1) % n2
    ang_u = _interior_angle_at(new_verts, nu)
    ang_v = _interior_angle_at(new_verts, nv)

    if reverse:
        score = abs((ang_b + ang_u) - 180.0) + abs((ang_a + ang_v) - 180.0)
    else:
        score = abs((ang_b + ang_v) - 180.0) + abs((ang_a + ang_u) - 180.0)
    return score * 0.5


def _edge_length_penalty(piece: AnalyzedPiece, edge_idx: int, seg_len: float) -> float:
    el = piece.edges[edge_idx].length_cm
    mid = (el + seg_len) / 2.0
    return abs(el - seg_len) / max(mid, 1e-6)


def _try_attach_with_angle(
    piece: AnalyzedPiece,
    placed_verts: np.ndarray,
    placed_edge: int,
    ep0: np.ndarray,
    ep1: np.ndarray,
) -> Optional[Tuple[np.ndarray, int, bool, float]]:
    verts = np.asarray(piece.vertices_cm, dtype=np.float64)
    seg_len = float(np.linalg.norm(ep1 - ep0))
    best: Optional[Tuple[np.ndarray, int, bool, float]] = None

    for ei in range(len(piece.edges)):
        len_pen = _edge_length_penalty(piece, ei, seg_len)
        if len_pen > 0.50:
            continue
        for reverse in (False, True):
            world = _align_edge_to_segment(verts, ei, ep1, ep0, reverse)
            if world is None:
                continue
            ang_score = _angle_complement_score(placed_verts, placed_edge, world, ei, reverse)
            score = ang_score + len_pen * 40.0
            if best is None or score < best[3]:
                best = (world, ei, reverse, score)
    return best


def _union_bbox(placed: List[PlacedPiece]) -> Tuple[float, float, float, float]:
    allp = np.vstack([p.vertices_cm for p in placed])
    return _bbox(allp)


def _coverage_stats(
    placed: List[PlacedPiece], ox: float, oy: float, w: float, h: float, grid: int = 28
) -> Tuple[float, int]:
    covered = 0
    double = 0
    total = grid * grid
    for x in np.linspace(ox, ox + w, grid):
        for y in np.linspace(oy, oy + h, grid):
            hits = sum(1 for p in placed if _point_in_poly(x, y, p.vertices_cm))
            if hits >= 1:
                covered += 1
            if hits > 1:
                double += 1
    return covered / max(total, 1), double


def _validate_assembly(placed: List[PlacedPiece], ox: float, oy: float, w: float, h: float) -> bool:
    if not placed:
        return False

    total = sum(_polygon_area(p.vertices_cm) for p in placed)
    target = w * h
    if abs(total - target) / max(target, 1e-6) > config.AREA_SUM_TOLERANCE:
        return False

    for p in placed:
        if not _vertices_inside(p.vertices_cm, ox, oy, w, h):
            return False

    bx0, by0, bx1, by1 = _union_bbox(placed)
    tol = 0.30
    if bx0 < ox - tol or by0 < oy - tol or bx1 > ox + w + tol or by1 > oy + h + tol:
        return False

    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if _overlap_area(placed[i].vertices_cm, placed[j].vertices_cm) > 0.04:
                return False

    coverage, double_hits = _coverage_stats(placed, ox, oy, w, h)
    if coverage < 0.90 or double_hits > 0:
        return False

    return all(_piece_has_boundary_edge(p.vertices_cm, ox, oy, w, h) for p in placed)


def _area_consistent(
    analyzed: List[AnalyzedPiece],
    placed: List[PlacedPiece],
    used: Set[int],
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> bool:
    target = w * h
    placed_area = sum(_polygon_area(p.vertices_cm) for p in placed)
    remaining = sum(analyzed[i].area_cm2 for i in range(len(analyzed)) if i not in used)
    return abs(placed_area + remaining - target) / max(target, 1e-6) <= config.AREA_SUM_TOLERANCE


def _vertices_inside_search(vertices: np.ndarray, ox: float, oy: float, w: float, h: float) -> bool:
    return _vertices_inside(vertices, ox, oy, w, h, tol=0.38)


def _collect_attach_candidates(
    analyzed: List[AnalyzedPiece],
    placed: List[PlacedPiece],
    used: Set[int],
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> List[Tuple[float, List[PlacedPiece], Set[int]]]:
    candidates: List[Tuple[float, List[PlacedPiece], Set[int]]] = []
    max_score = 55.0

    for exp_pi, exp_ei, ep0, ep1 in _exposed_edges(placed):
        partner_verts = placed[exp_pi].vertices_cm
        for pi, piece in enumerate(analyzed):
            if pi in used:
                continue
            result = _try_attach_with_angle(piece, partner_verts, exp_ei, ep0, ep1)
            if result is None:
                continue
            world, _, _, score = result
            if score > max_score:
                continue
            if not _vertices_inside_search(world, ox, oy, w, h):
                continue
            if _any_overlap(placed, world):
                continue

            new_placed = [
                PlacedPiece(p.piece_idx, p.vertices_cm.copy(), set(p.matched_edges))
                for p in placed
            ]
            new_placed[exp_pi].matched_edges.add(exp_ei)
            new_placed.append(PlacedPiece(pi, world, set()))
            new_used = set(used) | {pi}
            if not _area_consistent(analyzed, new_placed, new_used, ox, oy, w, h):
                continue
            candidates.append((score, new_placed, new_used))

    candidates.sort(key=lambda x: x[0])
    return candidates


def _backtrack_from_initial(
    analyzed: List[AnalyzedPiece],
    initial: List[PlacedPiece],
    used: Set[int],
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> Optional[List[PlacedPiece]]:
    n = len(analyzed)
    branch_limit = 14
    max_nodes = 1200

    def _search(placed: List[PlacedPiece], cur_used: Set[int], nodes: List[int]) -> Optional[List[PlacedPiece]]:
        if nodes[0] >= max_nodes:
            return None
        if len(cur_used) == n:
            return placed if _validate_assembly(placed, ox, oy, w, h) else None
        if not _area_consistent(analyzed, placed, cur_used, ox, oy, w, h):
            return None

        candidates = _collect_attach_candidates(analyzed, placed, cur_used, ox, oy, w, h)
        if not candidates:
            return None

        for _, new_placed, new_used in candidates[:branch_limit]:
            nodes[0] += 1
            result = _search(new_placed, new_used, nodes)
            if result is not None:
                return result
        return None

    return _search(initial, used, [0])


def _iter_seed_placements(
    analyzed: List[AnalyzedPiece],
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> List[Tuple[List[PlacedPiece], Set[int]]]:
    """生成首片种子的所有候选放置（直角四角 + 边界贴边）"""
    seeds: List[Tuple[List[PlacedPiece], Set[int]]] = []
    seen_keys: Set[str] = set()

    def _add(piece_idx: int, world: np.ndarray) -> None:
        if not _vertices_inside(world, ox, oy, w, h):
            return
        if not _piece_has_boundary_edge(world, ox, oy, w, h):
            return
        key = str(np.round(world, 2).tolist())
        if key in seen_keys:
            return
        seen_keys.add(key)
        seeds.append(([PlacedPiece(piece_idx, world, set())], {piece_idx}))

    corners = _target_corner_dirs(ox, oy, w, h)
    ranked = sorted(range(len(analyzed)), key=lambda i: analyzed[i].area_cm2, reverse=True)

    for pi in ranked:
        piece = analyzed[pi]
        for ci in _right_angle_corners(piece.vertices_cm):
            for corner_xy, da, db in corners:
                world = _align_right_angle_to_corner(piece.vertices_cm, ci, corner_xy, da, db)
                if world is not None:
                    _add(pi, world)

    for pi in ranked[:3]:
        piece = analyzed[pi]
        edge_order = sorted(range(len(piece.edges)), key=lambda ei: piece.edges[ei].length_cm, reverse=True)
        for ei in edge_order[:2]:
            for side in ("top", "bottom", "left", "right"):
                for slide in (0.0, 1.0):
                    world = _align_edge_to_boundary(piece.vertices_cm, ei, side, ox, oy, w, h, slide)
                    if world is not None:
                        _add(pi, world)

    return seeds


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        return True

    def copy(self) -> "_UnionFind":
        uf = _UnionFind(len(self.parent))
        uf.parent = self.parent.copy()
        return uf


def _edge_pair_candidates(analyzed: List[AnalyzedPiece], rel_tol: float = 0.22) -> List[Tuple[Tuple[int, int], Tuple[int, int], float]]:
    """边长相近的跨片边对，作为拼合邻接候选"""
    edges: List[Tuple[int, int, float]] = []
    for pi, piece in enumerate(analyzed):
        for ei, edge in enumerate(piece.edges):
            edges.append((pi, ei, edge.length_cm))

    pairs: List[Tuple[Tuple[int, int], Tuple[int, int], float]] = []
    for i in range(len(edges)):
        pi, ei, li = edges[i]
        for j in range(i + 1, len(edges)):
            pj, ej, lj = edges[j]
            if pi == pj:
                continue
            mid = (li + lj) / 2.0
            if mid < 1e-6:
                continue
            err = abs(li - lj) / mid
            if err <= rel_tol:
                pairs.append(((pi, ei), (pj, ej), err))
    pairs.sort(key=lambda x: x[2])
    return pairs


def _spanning_edge_sets(n: int, pairs: List, limit: int = 160) -> List[List[Tuple[int, int, int, int]]]:
    """从边对中选取 n-1 条构成生成树"""
    results: List[List[Tuple[int, int, int, int]]] = []

    def dfs(start: int, chosen: List[Tuple[int, int, int, int]], uf: _UnionFind) -> bool:
        if len(chosen) == n - 1:
            if uf.find(0) == uf.find(n - 1) and len({uf.find(i) for i in range(n)}) == 1:
                results.append(list(chosen))
            return len(results) >= limit

        for k in range(start, len(pairs)):
            (pi, ei), (pj, ej), _ = pairs[k]
            if uf.find(pi) == uf.find(pj):
                continue
            uf2 = uf.copy()
            uf2.union(pi, pj)
            chosen.append((pi, ei, pj, ej))
            if dfs(k + 1, chosen, uf2):
                return True
            chosen.pop()
        return False

    if n <= 1:
        return [[]]
    dfs(0, [], _UnionFind(n))
    return results


def _attach_known_edge(
    analyzed: List[AnalyzedPiece],
    host: PlacedPiece,
    host_edge: int,
    guest_idx: int,
    guest_edge: int,
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> Optional[np.ndarray]:
    verts_host = host.vertices_cm
    n = len(verts_host)
    ep0 = verts_host[host_edge]
    ep1 = verts_host[(host_edge + 1) % n]
    guest = analyzed[guest_idx]
    gverts = np.asarray(guest.vertices_cm, dtype=np.float64)

    for reverse in (False, True):
        world = _align_edge_to_segment(gverts, guest_edge, ep1, ep0, reverse)
        if world is None:
            continue
        if not _vertices_inside_search(world, ox, oy, w, h):
            continue
        if _any_overlap([host], world):
            continue
        return world
    return None


def _assemble_from_tree(
    analyzed: List[AnalyzedPiece],
    tree_edges: List[Tuple[int, int, int, int]],
    root: int,
    root_world: np.ndarray,
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> Optional[List[PlacedPiece]]:
    n = len(analyzed)
    adj: List[List[Tuple[int, int, int]]] = [[] for _ in range(n)]
    for pi, ei, pj, ej in tree_edges:
        adj[pi].append((pj, ei, ej))
        adj[pj].append((pi, ej, ei))

    placed_map: dict[int, PlacedPiece] = {root: PlacedPiece(root, root_world.copy(), set())}
    queue = [root]

    while queue:
        pi = queue.pop(0)
        host = placed_map[pi]
        for pj, ei_on_host, ej_on_guest in adj[pi]:
            if pj in placed_map:
                continue
            if ei_on_host in host.matched_edges:
                continue
            world = _attach_known_edge(analyzed, host, ei_on_host, pj, ej_on_guest, ox, oy, w, h)
            if world is None:
                return None
            guest = PlacedPiece(pj, world, set())
            host.matched_edges.add(ei_on_host)
            placed_map[pj] = guest
            queue.append(pj)

    if len(placed_map) != n:
        return None
    return list(placed_map.values())


def _seed_worlds_for_piece(
    analyzed: List[AnalyzedPiece], piece_idx: int, ox: float, oy: float, w: float, h: float
) -> List[np.ndarray]:
    worlds: List[np.ndarray] = []
    seen: Set[str] = set()
    piece = analyzed[piece_idx]

    def _push(world: Optional[np.ndarray]) -> None:
        if world is None:
            return
        if not _vertices_inside_search(world, ox, oy, w, h):
            return
        if not _piece_has_boundary_edge(world, ox, oy, w, h):
            return
        key = str(np.round(world, 2).tolist())
        if key in seen:
            return
        seen.add(key)
        worlds.append(world)

    for ci in _right_angle_corners(piece.vertices_cm):
        for corner_xy, da, db in _target_corner_dirs(ox, oy, w, h):
            _push(_align_right_angle_to_corner(piece.vertices_cm, ci, corner_xy, da, db))

    edge_order = sorted(range(len(piece.edges)), key=lambda ei: piece.edges[ei].length_cm, reverse=True)
    for ei in edge_order[:2]:
        for side in ("top", "bottom", "left", "right"):
            for slide in (0.0, 1.0):
                _push(_align_edge_to_boundary(piece.vertices_cm, ei, side, ox, oy, w, h, slide))
    return worlds


def _solve_by_edge_tree(
    analyzed: List[AnalyzedPiece],
    ox: float,
    oy: float,
    w: float,
    h: float,
) -> Optional[List[PlacedPiece]]:
    """边长匹配生成树 + BFS 刚性拼合（无 seed）"""
    n = len(analyzed)
    if n == 1:
        for world in _seed_worlds_for_piece(analyzed, 0, ox, oy, w, h):
            placed = [PlacedPiece(0, world, set())]
            if _validate_assembly(placed, ox, oy, w, h):
                return placed
        return None

    pairs = _edge_pair_candidates(analyzed)
    if len(pairs) < n - 1:
        return None

    trees = _spanning_edge_sets(n, pairs, limit=48)
    root_order = sorted(range(n), key=lambda i: analyzed[i].area_cm2, reverse=True)[:2]

    for tree in trees:
        for root in root_order:
            for root_world in _seed_worlds_for_piece(analyzed, root, ox, oy, w, h)[:10]:
                placed = _assemble_from_tree(analyzed, tree, root, root_world, ox, oy, w, h)
                if placed is not None and _validate_assembly(placed, ox, oy, w, h):
                    return placed
    return None


def _solve_by_random_restarts(
    analyzed: List[AnalyzedPiece],
    w: float,
    h: float,
    ox: float,
    oy: float,
    attempts: int = 32,
) -> Optional[List[PlacedPiece]]:
    """随机分支回溯：应对检测边长误差导致的确定性搜索失败"""
    import random

    seeds = _iter_seed_placements(analyzed, ox, oy, w, h)
    if not seeds:
        return None
    n = len(analyzed)
    rng = random.Random(2026)

    for _ in range(attempts):
        initial, used = rng.choice(seeds)
        placed = [PlacedPiece(p.piece_idx, p.vertices_cm.copy(), set(p.matched_edges)) for p in initial]
        cur_used = set(used)
        failed = False
        while len(cur_used) < n:
            cands = _collect_attach_candidates(analyzed, placed, cur_used, ox, oy, w, h)
            if not cands:
                failed = True
                break
            pick = rng.choice(cands[: min(8, len(cands))])
            _, placed, cur_used = pick
        if not failed and _validate_assembly(placed, ox, oy, w, h):
            return placed
    return None


def _solve_for_size(
    analyzed: List[AnalyzedPiece],
    w: float,
    h: float,
    ox: float,
    oy: float,
) -> Optional[List[PlacedPiece]]:
    result = _solve_by_edge_tree(analyzed, ox, oy, w, h)
    if result is not None:
        return result
    for initial, used in _iter_seed_placements(analyzed, ox, oy, w, h)[:16]:
        result = _backtrack_from_initial(analyzed, initial, used, ox, oy, w, h)
        if result is not None:
            return result
    return _solve_by_random_restarts(analyzed, w, h, ox, oy, attempts=48)


def solve_assembly(
    analyzed: List[AnalyzedPiece],
    width_cm: Optional[float] = None,
    height_cm: Optional[float] = None,
) -> Optional[Tuple[float, float, Tuple[float, float], List[PlacedPiece]]]:
    if not analyzed:
        return None

    size_cands: List[Tuple[float, float]] = []
    if width_cm is not None and height_cm is not None:
        size_cands = [(float(width_cm), float(height_cm))]
    else:
        from .target import candidate_target_sizes

        total = sum(p.area_cm2 for p in analyzed)
        size_cands = [(w, h) for w, h, _ in candidate_target_sizes(total)[:10]]

    for w, h in size_cands:
        ox, oy = target_origin_for_size(w)
        result = _solve_for_size(analyzed, w, h, ox, oy)
        if result is not None:
            return w, h, (ox, oy), result
    return None


def build_assignments(
    detected: List[DetectedPiece],
    analyzed: List[AnalyzedPiece],
    placed: List[PlacedPiece],
) -> List[PieceAssignment]:
    idx_map = {i: a for i, a in enumerate(analyzed)}
    assignments: List[PieceAssignment] = []
    for pp in placed:
        ap = idx_map[pp.piece_idx]
        det_idx = ap.index
        target_v = pp.vertices_cm
        center = polygon_centroid(target_v)
        aligned = rigid_align_no_flip(detected[det_idx].vertices_cm, target_v)
        from .geometry import max_vertex_error

        err = max_vertex_error(aligned, target_v, n=min(32, len(target_v) * 4))
        assignments.append(
            PieceAssignment(
                detected_index=det_idx,
                template_name=f"Q2#{det_idx}",
                target_center_cm=center,
                target_angle_deg=0.0,
                target_vertices_cm=target_v,
                match_score=1.0,
                vertex_error_cm=err,
            )
        )
    return assignments


def evaluate_assembly_q2(
    detected: List[DetectedPiece],
    assignments: List[PieceAssignment],
    target_size: Tuple[float, float],
    target_origin: Tuple[float, float],
) -> dict:
    from .geometry import max_vertex_error

    errors = []
    for asg in assignments:
        pi = asg.detected_index
        if pi >= len(detected) or len(asg.target_vertices_cm) == 0:
            continue
        aligned = rigid_align_no_flip(detected[pi].vertices_cm, asg.target_vertices_cm)
        errors.append(max_vertex_error(aligned, asg.target_vertices_cm))

    w, h = target_size
    total_area = sum(_polygon_area(a.target_vertices_cm) for a in assignments)
    area_ok = abs(total_area - w * h) / (w * h) <= config.AREA_SUM_TOLERANCE

    max_err = float(max(errors)) if errors else 999.0
    ox, oy = target_origin
    placed_for_geom = [PlacedPiece(0, a.target_vertices_cm, set()) for a in assignments]
    geometry_ok = _validate_assembly(placed_for_geom, ox, oy, w, h) if placed_for_geom else False
    coverage, _ = _coverage_stats(placed_for_geom, ox, oy, w, h) if placed_for_geom else (0.0, 0)

    assembly_ok = (
        len(assignments) == len(detected)
        and max_err <= config.VERTEX_MATCH_TOLERANCE_CM
        and area_ok
        and geometry_ok
    )
    return {
        "assembly_ok": assembly_ok,
        "max_vertex_error_cm": max_err,
        "area_ok": area_ok,
        "geometry_ok": geometry_ok,
        "coverage_ratio": coverage,
        "target_width_cm": w,
        "target_height_cm": h,
        "piece_count": len(assignments),
    }
