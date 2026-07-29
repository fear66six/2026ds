"""拼图求解：匹配检测碎片与模板，生成精确目标顶点"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from . import config
from .geometry import (
    compute_rigid_align_error,
    max_vertex_error,
    polygon_centroid,
    resample_polygon,
    rigid_align_no_flip,
)
from .pieces import PIECE_TEMPLATES, PieceTemplate, get_template
from .vision import DetectedPiece


@dataclass
class PieceAssignment:
    detected_index: int
    template_name: str
    target_center_cm: Optional[Tuple[float, float]]
    target_angle_deg: float
    target_vertices_cm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    match_score: float = 0.0
    vertex_error_cm: float = 0.0


def template_world_vertices(tpl: PieceTemplate, target_origin: Tuple[float, float]) -> np.ndarray:
    ox, oy = target_origin
    return tpl.world_vertices((ox, oy), 0.0)


def _vertex_count(piece: DetectedPiece) -> int:
    return len(piece.vertices_cm)


def _template_vertex_count(tpl: PieceTemplate) -> int:
    return len(tpl.local_vertices)


def _assignment_cost(
    piece: DetectedPiece,
    tpl: PieceTemplate,
    target_origin: Tuple[float, float],
) -> Tuple[float, float, float]:
    """返回 (代价, 最大对齐误差, 旋转角)"""
    target_verts = template_world_vertices(tpl, target_origin)
    max_err, rot_deg = compute_rigid_align_error(piece.vertices_cm, target_verts)
    aligned = rigid_align_no_flip(piece.vertices_cm, target_verts)

    area_ratio = piece.area_cm2 / max(tpl.area, 0.1)
    area_pen = abs(np.log(max(area_ratio, 0.05))) * 0.5

    vtx_pen = abs(_vertex_count(piece) - _template_vertex_count(tpl)) * 2.0
    if _template_vertex_count(tpl) == 3 and _vertex_count(piece) != 3:
        vtx_pen += 3.0

    cost = max_err * 1.5 + area_pen + vtx_pen
    return cost, max_err, rot_deg


def _build_assignment(
    piece: DetectedPiece,
    tpl: PieceTemplate,
    target_origin: Tuple[float, float],
) -> PieceAssignment:
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


def assign_pieces(
    pieces: List[DetectedPiece],
    target_origin: Tuple[float, float],
) -> List[PieceAssignment]:
    n = min(len(pieces), len(PIECE_TEMPLATES))
    piece_indices = list(range(len(pieces)))
    template_names = [t.name for t in PIECE_TEMPLATES]

    best_assignments: List[PieceAssignment] = []
    best_total = float("inf")
    # 每个“检测碎片×固定模板”的刚性误差与排列无关。旧实现会在4!枚举中
    # 重复计算同一组合6次；缓存4×4结果可保持判定完全一致并显著降低耗时。
    cached: dict[tuple[int, str], PieceAssignment] = {}
    for piece_index in piece_indices[:n]:
        for template_name in template_names:
            assignment = _build_assignment(
                pieces[piece_index],
                get_template(template_name),
                target_origin,
            )
            assignment.detected_index = piece_index
            cached[(piece_index, template_name)] = assignment

    for perm in itertools.permutations(template_names, n):
        assignments: List[PieceAssignment] = []
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
    pieces: List[DetectedPiece],
    assignments: List[PieceAssignment],
    target_origin: Tuple[float, float],
    final_vertices: Optional[dict[int, np.ndarray]] = None,
) -> dict:
    ox, oy = target_origin
    target_box = (
        ox,
        oy,
        ox + config.TARGET_WIDTH_CM,
        oy + config.TARGET_HEIGHT_CM,
    )

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
    assembly_ok = max_err <= config.VERTEX_MATCH_TOLERANCE_CM

    return {
        "all_in_lower_half": all_in_lower,
        "move_phase_ok": all_in_lower,
        "assembly_ok": assembly_ok,
        "avg_vertex_error_cm": avg_err,
        "max_vertex_error_cm": max_err,
        "avg_center_error_cm": avg_err,
        "max_center_error_cm": max_err,
        "target_box_cm": target_box,
        "piece_count": len(pieces),
        "expected_count": len(PIECE_TEMPLATES),
    }


def get_assignment_map(assignments: List[PieceAssignment]) -> dict[int, PieceAssignment]:
    return {a.detected_index: a for a in assignments}
