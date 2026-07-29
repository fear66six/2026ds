"""图2 四片模板匹配（test.png 等 fig2 场景可选回退）"""

from __future__ import annotations

import itertools
from typing import List, Optional, Tuple

import numpy as np

from . import config
from .assignment import PieceAssignment
from .geometry import compute_rigid_align_error, max_vertex_error, polygon_centroid, rigid_align_no_flip
from .piece import analyze_pieces
from .target import target_origin_for_size
from .templates import PIECE_TEMPLATES, PieceTemplate, get_template
from .vision import DetectedPiece

def _template_world_vertices(tpl: PieceTemplate, target_origin: Tuple[float, float]) -> np.ndarray:
    ox, oy = target_origin
    return tpl.world_vertices((ox, oy), 0.0)


def _assignment_cost(
    piece: DetectedPiece,
    tpl: PieceTemplate,
    target_origin: Tuple[float, float],
) -> Tuple[float, float, float]:
    target_verts = _template_world_vertices(tpl, target_origin)
    max_err, rot_deg = compute_rigid_align_error(piece.vertices_cm, target_verts)
    area_ratio = piece.area_cm2 / max(tpl.area, 0.1)
    area_pen = abs(np.log(max(area_ratio, 0.05))) * 0.5
    vtx_pen = abs(len(piece.vertices_cm) - len(tpl.local_vertices)) * 2.0
    if len(tpl.local_vertices) == 3 and len(piece.vertices_cm) != 3:
        vtx_pen += 3.0
    cost = max_err * 1.5 + area_pen + vtx_pen
    return cost, max_err, rot_deg


def _build_assignment(
    piece: DetectedPiece,
    tpl: PieceTemplate,
    target_origin: Tuple[float, float],
) -> PieceAssignment:
    target_verts = _template_world_vertices(tpl, target_origin)
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


def assign_fig2_templates(
    pieces: List[DetectedPiece],
    target_origin: Tuple[float, float],
) -> List[PieceAssignment]:
    n = min(len(pieces), len(PIECE_TEMPLATES))
    best_assignments: List[PieceAssignment] = []
    best_total = float("inf")
    template_names = [t.name for t in PIECE_TEMPLATES]

    for perm in itertools.permutations(template_names, n):
        assignments: List[PieceAssignment] = []
        total = 0.0
        for pi, tpl_name in zip(range(len(pieces))[:n], perm):
            tpl = get_template(tpl_name)
            asg = _build_assignment(pieces[pi], tpl, target_origin)
            asg.detected_index = pi
            assignments.append(asg)
            total += asg.match_score
        if total < best_total:
            best_total = total
            best_assignments = assignments

    return best_assignments


def try_template_fallback(
    pieces: List[DetectedPiece],
    target_width: Optional[float] = None,
    target_height: Optional[float] = None,
) -> Optional[Tuple[float, float, Tuple[float, float], List[PieceAssignment]]]:
    if len(pieces) != 4:
        return None
    if len(analyze_pieces(pieces)) < 3:
        return None

    tw = float(target_width or 10.0)
    th = float(target_height or 6.0)
    origin = target_origin_for_size(tw)
    assignments = assign_fig2_templates(pieces, origin)
    if len(assignments) != 4:
        return None

    errors = []
    for asg in assignments:
        pi = asg.detected_index
        if pi >= len(pieces):
            continue
        aligned = rigid_align_no_flip(pieces[pi].vertices_cm, asg.target_vertices_cm)
        errors.append(max_vertex_error(aligned, asg.target_vertices_cm))
    if not errors or max(errors) > config.VERTEX_MATCH_TOLERANCE_CM * 1.8:
        return None
    return tw, th, origin, assignments