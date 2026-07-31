"""拼图求解：全局 C(N,4)×4! 模板分配与精确目标顶点。"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from . import config
from .geometry import (
    compute_rigid_align_error,
    compute_rigid_transform,
    max_vertex_error,
    polygon_centroid,
    resample_polygon,
    rigid_align_no_flip,
)
from .models import PieceGeometry
from .pieces import PIECE_TEMPLATES, PieceTemplate, get_template, template_target_vertices_mm


TEMPLATE_IDS = ("P1", "P2", "P3", "P4")


@dataclass
class PieceAssignment:
    detected_index: int
    template_name: str
    target_center_cm: tuple[float, float] | None
    target_angle_deg: float
    target_vertices_cm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    match_score: float = 0.0
    vertex_error_cm: float = 0.0


@dataclass
class TemplateAssignmentResult:
    accepted: bool
    assignments: dict[str, PieceGeometry]
    selected_candidate_ids: list[int]
    rejected_candidate_ids: list[int]
    total_cost: float
    second_best_cost: float
    confidence_margin: float
    rejection_reason: str | None
    pairwise_costs: dict[tuple[int, str], float] = field(default_factory=dict)
    rejected_reasons: dict[int, str] = field(default_factory=dict)


@dataclass
class _TemplateFeatures:
    template_id: str
    template_name: str
    vertex_count: int
    area_mm2: float
    perimeter_mm: float
    convexity: float
    edge_lengths_norm: np.ndarray
    inner_angles_deg: np.ndarray
    edge_ratios: np.ndarray
    resampled_mm: np.ndarray
    target_vertices_mm: np.ndarray
    target_center_mm: np.ndarray


_FEATURE_CACHE: dict[tuple[float, float, float], dict[str, _TemplateFeatures]] = {}


def template_world_vertices(tpl: PieceTemplate, target_origin: tuple[float, float]) -> np.ndarray:
    ox, oy = target_origin
    return tpl.world_vertices((ox, oy), 0.0)


def _edge_angle_features(vertices_mm: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    pts = np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 2)
    edges = np.roll(pts, -1, axis=0) - pts
    lengths = np.linalg.norm(edges, axis=1)
    previous = -np.roll(edges, 1, axis=0)
    denom = np.linalg.norm(previous, axis=1) * np.maximum(lengths, 1e-9)
    cosines = np.clip(np.sum(previous * edges, axis=1) / np.maximum(denom, 1e-9), -1.0, 1.0)
    angles = np.degrees(np.arccos(cosines))
    mean_len = float(np.mean(lengths)) if len(lengths) else 1.0
    norm = lengths / max(mean_len, 1e-9)
    ratios = lengths / np.maximum(np.roll(lengths, 1), 1e-9)
    return norm, angles, ratios


def _cyclic_l1(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    if len(a) != len(b) or len(a) == 0:
        return float("inf")
    best = float("inf")
    for rev in (False, True):
        seq = a[::-1] if rev else a
        for shift in range(len(seq)):
            best = min(best, float(np.mean(np.abs(np.roll(seq, shift) - b))))
    return best


def _get_template_features(
    origin_mm: tuple[float, float],
    scale: float = 1.0,
) -> dict[str, _TemplateFeatures]:
    key = (float(origin_mm[0]), float(origin_mm[1]), float(scale))
    cached = _FEATURE_CACHE.get(key)
    if cached is not None:
        return cached
    features: dict[str, _TemplateFeatures] = {}
    for index, tpl in enumerate(PIECE_TEMPLATES):
        tid = f"P{index + 1}"
        verts = template_target_vertices_mm(index, origin_mm, scale)
        area = float(abs(_polygon_area(verts)))
        peri = float(np.sum(np.linalg.norm(np.roll(verts, -1, axis=0) - verts, axis=1)))
        hull = verts  # templates are convex by construction
        hull_area = area
        edges_n, angles, ratios = _edge_angle_features(verts)
        features[tid] = _TemplateFeatures(
            template_id=tid,
            template_name=tpl.name,
            vertex_count=len(verts),
            area_mm2=area,
            perimeter_mm=peri,
            convexity=float(area / max(hull_area, 1e-9)),
            edge_lengths_norm=edges_n,
            inner_angles_deg=angles,
            edge_ratios=ratios,
            resampled_mm=resample_polygon(verts, 64),
            target_vertices_mm=verts,
            target_center_mm=np.mean(verts, axis=0),
        )
    _FEATURE_CACHE[key] = features
    return features


def _polygon_area(vertices: np.ndarray) -> float:
    pts = np.asarray(vertices, dtype=np.float64)
    return 0.5 * float(np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1)))


def _pair_cost(
    piece: PieceGeometry,
    feat: _TemplateFeatures,
) -> tuple[float, str | None]:
    n_src = len(np.asarray(piece.vertices_mm).reshape(-1, 2))
    if n_src not in (3, 4):
        return float("inf"), "INVALID_VERTEX_COUNT"
    if n_src != feat.vertex_count:
        return float("inf"), "TRIANGLE_QUAD_MISMATCH"
    if piece.touches_boundary or piece.inside_ratio < config.MIN_INSIDE_RATIO:
        return float("inf"), piece.rejection_reason or "BOUNDARY_OR_ROI"
    area_rel = abs(piece.area_mm2 - feat.area_mm2) / max(feat.area_mm2, 1e-6)
    if area_rel > config.MAX_AREA_RELATIVE_ERROR:
        return float("inf"), "AREA_ERROR"
    edges_n, angles, ratios = _edge_angle_features(piece.vertices_mm)
    edge_err = _cyclic_l1(edges_n, feat.edge_lengths_norm)
    angle_err = _cyclic_l1(angles, feat.inner_angles_deg) / 180.0
    ratio_err = _cyclic_l1(ratios, feat.edge_ratios)
    transform = compute_rigid_transform(piece.vertices_mm, feat.target_vertices_mm)
    if not transform.valid or transform.mirrored or transform.determinant <= 0:
        return float("inf"), transform.rejection_reason or "MIRRORED"
    vertex_rms = transform.rms_error_mm / max(np.sqrt(feat.area_mm2), 1.0)
    src_rs = resample_polygon(piece.vertices_mm, 64)
    chamfer = float(np.mean(np.min(np.linalg.norm(src_rs[:, None, :] - feat.resampled_mm[None, :, :], axis=2), axis=1)))
    chamfer /= max(np.sqrt(feat.area_mm2), 1.0)
    boundary_pen = 0.0 if not piece.touches_boundary else 1.0
    cost = (
        config.W_AREA * area_rel
        + config.W_EDGE * (edge_err + 0.25 * ratio_err)
        + config.W_ANGLE * angle_err
        + config.W_VERTEX * vertex_rms
        + config.W_CONTOUR * chamfer
        + config.W_BOUNDARY * boundary_pen
    )
    return float(cost), None


def assign_templates_global(
    candidates: list[PieceGeometry],
    *,
    origin_mm: tuple[float, float],
    scale: float = 1.0,
    max_cost: float | None = None,
    min_margin: float | None = None,
) -> TemplateAssignmentResult:
    """对 N 个候选枚举 C(N,4)×4!，选择全局最优模板分配。"""
    max_cost = config.MAX_GLOBAL_ASSIGNMENT_COST if max_cost is None else max_cost
    min_margin = config.MIN_ASSIGNMENT_MARGIN if min_margin is None else min_margin
    features = _get_template_features(origin_mm, scale)
    template_ids = list(TEMPLATE_IDS)
    n = len(candidates)
    empty = TemplateAssignmentResult(
        accepted=False,
        assignments={},
        selected_candidate_ids=[],
        rejected_candidate_ids=list(range(n)),
        total_cost=float("inf"),
        second_best_cost=float("inf"),
        confidence_margin=0.0,
        rejection_reason="TOO_FEW_CANDIDATES" if n < 4 else "NO_FEASIBLE_ASSIGNMENT",
    )
    if n < 4:
        return empty

    pairwise: dict[tuple[int, str], float] = {}
    reject_pair: dict[tuple[int, str], str] = {}
    for i, piece in enumerate(candidates):
        for tid in template_ids:
            cost, reason = _pair_cost(piece, features[tid])
            pairwise[(i, tid)] = cost
            if reason:
                reject_pair[(i, tid)] = reason

    ranked: list[tuple[float, tuple[int, ...], tuple[str, ...]]] = []
    for combo in itertools.combinations(range(n), 4):
        for perm in itertools.permutations(template_ids, 4):
            total = 0.0
            feasible = True
            for idx, tid in zip(combo, perm):
                c = pairwise[(idx, tid)]
                if not np.isfinite(c):
                    feasible = False
                    break
                total += c
            if feasible:
                ranked.append((total, combo, perm))
    if not ranked:
        rejected_reasons = {
            i: next((reject_pair[(i, t)] for t in template_ids if (i, t) in reject_pair), "UNMATCHABLE")
            for i in range(n)
        }
        return TemplateAssignmentResult(
            accepted=False,
            assignments={},
            selected_candidate_ids=[],
            rejected_candidate_ids=list(range(n)),
            total_cost=float("inf"),
            second_best_cost=float("inf"),
            confidence_margin=0.0,
            rejection_reason="NO_FEASIBLE_ASSIGNMENT",
            pairwise_costs=pairwise,
            rejected_reasons=rejected_reasons,
        )

    ranked.sort(key=lambda item: item[0])
    best_cost, best_combo, best_perm = ranked[0]
    second_cost = ranked[1][0] if len(ranked) > 1 else float("inf")
    margin = second_cost - best_cost if np.isfinite(second_cost) else float("inf")
    if best_cost > max_cost:
        return TemplateAssignmentResult(
            accepted=False,
            assignments={},
            selected_candidate_ids=list(best_combo),
            rejected_candidate_ids=[i for i in range(n) if i not in best_combo],
            total_cost=best_cost,
            second_best_cost=second_cost,
            confidence_margin=margin,
            rejection_reason="MAX_GLOBAL_ASSIGNMENT_COST",
            pairwise_costs=pairwise,
        )
    if margin < min_margin:
        return TemplateAssignmentResult(
            accepted=False,
            assignments={},
            selected_candidate_ids=list(best_combo),
            rejected_candidate_ids=[i for i in range(n) if i not in best_combo],
            total_cost=best_cost,
            second_best_cost=second_cost,
            confidence_margin=margin,
            rejection_reason="PIECE_IDENTITY_AMBIGUOUS",
            pairwise_costs=pairwise,
        )

    assignments: dict[str, PieceGeometry] = {}
    for idx, tid in zip(best_combo, best_perm):
        piece = candidates[idx]
        piece.template_id = tid
        piece.template_match_score = pairwise[(idx, tid)]
        piece.confidence = max(0.0, 1.0 - pairwise[(idx, tid)] / max(max_cost, 1e-6))
        assignments[tid] = piece
    selected = list(best_combo)
    rejected = [i for i in range(n) if i not in selected]
    rejected_reasons = {i: "NOT_IN_BEST_QUARTET" for i in rejected}
    return TemplateAssignmentResult(
        accepted=True,
        assignments=assignments,
        selected_candidate_ids=selected,
        rejected_candidate_ids=rejected,
        total_cost=best_cost,
        second_best_cost=second_cost,
        confidence_margin=margin,
        rejection_reason=None,
        pairwise_costs=pairwise,
        rejected_reasons=rejected_reasons,
    )


def _vertex_count(piece) -> int:
    return len(piece.vertices_cm)


def _template_vertex_count(tpl: PieceTemplate) -> int:
    return len(tpl.local_vertices)


def _assignment_cost(piece, tpl: PieceTemplate, target_origin: tuple[float, float]):
    target_verts = template_world_vertices(tpl, target_origin)
    max_err, rot_deg = compute_rigid_align_error(piece.vertices_cm, target_verts)
    area_ratio = piece.area_cm2 / max(tpl.area, 0.1)
    area_pen = abs(np.log(max(area_ratio, 0.05))) * 0.5
    vtx_pen = abs(_vertex_count(piece) - _template_vertex_count(tpl)) * 2.0
    if _template_vertex_count(tpl) == 3 and _vertex_count(piece) != 3:
        vtx_pen += 3.0
    cost = max_err * 1.5 + area_pen + vtx_pen
    return cost, max_err, rot_deg


def _build_assignment(piece, tpl: PieceTemplate, target_origin: tuple[float, float]) -> PieceAssignment:
    target_verts = template_world_vertices(tpl, target_origin)
    center = polygon_centroid(target_verts)
    cost, align_err, rot_deg = _assignment_cost(piece, tpl, target_origin)
    return PieceAssignment(
        detected_index=-1,
        template_name=tpl.name,
        target_center_cm=center,
        target_angle_deg=rot_deg,
        target_vertices_cm=target_verts,
        match_score=cost,
        vertex_error_cm=align_err,
    )


def assign_pieces(pieces: list, target_origin: tuple[float, float]) -> list[PieceAssignment]:
    """兼容旧视觉 DetectedPiece 接口：对前 min(N,4) 做排列搜索。

    正式静态分析应使用 assign_templates_global。
    """
    n = min(len(pieces), len(PIECE_TEMPLATES))
    piece_indices = list(range(len(pieces)))
    template_names = [t.name for t in PIECE_TEMPLATES]
    best_assignments: list[PieceAssignment] = []
    best_total = float("inf")
    cached: dict[tuple[int, str], PieceAssignment] = {}
    for piece_index in piece_indices[:n]:
        for template_name in template_names:
            assignment = _build_assignment(pieces[piece_index], get_template(template_name), target_origin)
            assignment.detected_index = piece_index
            cached[(piece_index, template_name)] = assignment
    for perm in itertools.permutations(template_names, n):
        assignments: list[PieceAssignment] = []
        total = 0.0
        for pi, tpl_name in zip(piece_indices[:n], perm):
            asg = cached[(pi, tpl_name)]
            assignments.append(asg)
            total += asg.match_score
        if total < best_total:
            best_total = total
            best_assignments = assignments
    return best_assignments


def evaluate_assembly(
    pieces: list,
    assignments: list[PieceAssignment],
    target_origin: tuple[float, float],
    final_vertices: dict[int, np.ndarray] | None = None,
) -> dict:
    ox, oy = target_origin
    target_box = (ox, oy, ox + config.TARGET_WIDTH_CM, oy + config.TARGET_HEIGHT_CM)
    all_in_lower = all(not p.in_upper_half for p in pieces)
    errors = []
    for asg in assignments:
        if len(asg.target_vertices_cm) == 0:
            continue
        piece = pieces[asg.detected_index]
        if final_vertices and asg.detected_index in final_vertices:
            aligned = final_vertices[asg.detected_index]
        else:
            aligned = rigid_align_no_flip(piece.vertices_cm, asg.target_vertices_cm)
        err = max_vertex_error(aligned, asg.target_vertices_cm)
        errors.append(err)
    avg_err = float(np.mean(errors)) if errors else 999.0
    max_err = float(np.max(errors)) if errors else 999.0
    return {
        "all_in_lower_half": all_in_lower,
        "move_phase_ok": all_in_lower,
        "assembly_ok": max_err <= config.VERTEX_MATCH_TOLERANCE_CM,
        "avg_vertex_error_cm": avg_err,
        "max_vertex_error_cm": max_err,
        "avg_center_error_cm": avg_err,
        "max_center_error_cm": max_err,
        "target_box_cm": target_box,
        "piece_count": len(pieces),
        "expected_count": len(PIECE_TEMPLATES),
    }


def get_assignment_map(assignments: list[PieceAssignment]) -> dict[int, PieceAssignment]:
    return {a.detected_index: a for a in assignments}
