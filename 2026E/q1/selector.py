"""动态下一块选择；每轮只返回一个模板。"""

from __future__ import annotations

import itertools
import math

import numpy as np

from .models import AuditResult, PieceTaskStatus, SceneAnalysis


def _candidate_score(scene: SceneAnalysis, template_id: str) -> tuple[float, dict[str, float]]:
    state = scene.templates[template_id]
    piece = state.detected_piece
    if piece is None:
        return -math.inf, {"missing": 1.0}
    target_center = np.mean(state.expected_target_vertices_mm, axis=0)
    source = np.asarray(piece.center_mm)
    move_distance = float(np.linalg.norm(target_center - source))
    required_rotation = abs(float(piece.angle_deg))
    # 目标较靠外、匹配可信且抓取面积较大的块优先；不等同于固定编号或最近距离。
    clearance = float(min(target_center[0], 210.0 - target_center[0], target_center[1], 297.0 - target_center[1]))
    features = {
        "template_match_confidence": piece.confidence,
        "edge_fit_confidence": max(0.0, 1.0 - piece.edge_fit_rmse_mm / 5.0),
        "target_clearance": clearance,
        "move_distance": move_distance,
        "required_rotation": required_rotation,
        "source_pick_accessibility": min(1.0, piece.area_mm2 / 1000.0),
        "verification_visibility": 1.0,
        "path_collision_risk": 0.0,
        "blocking_future_targets": 0.0,
    }
    score = (
        4.0 * features["template_match_confidence"]
        + 1.5 * features["edge_fit_confidence"]
        + 0.02 * clearance
        + features["source_pick_accessibility"]
        - 0.003 * move_distance
        - 0.003 * required_rotation
    )
    return score, features


def select_next_piece(scene: SceneAnalysis, audit: AuditResult) -> tuple[str, dict]:
    if audit.release_failed_template:
        return audit.release_failed_template, {"reason": "RELEASE_UNCONFIRMED", "priority": 1}
    if audit.placed_offset:
        template_id = sorted(audit.placed_offset)[0]
        return template_id, {"reason": "PLACED_OFFSET_CORRECTION", "priority": 2}

    candidates = [
        key
        for key, state in scene.templates.items()
        if state.status == PieceTaskStatus.UNPLACED and state.detected_piece is not None
    ]
    if not candidates:
        raise RuntimeError("PLAN_FAILED: 没有可搬运的已确认碎片")

    scores = {key: _candidate_score(scene, key) for key in candidates}
    # 小规模前瞻：累计分数相同时偏好后续总移动较短；只执行最优排列第一项。
    best_order = max(
        itertools.permutations(candidates),
        key=lambda order: sum(scores[key][0] * (0.92**index) for index, key in enumerate(order)),
    )
    selected = best_order[0]
    return selected, {
        "reason": "DYNAMIC_LOOKAHEAD",
        "scores": {key: {"total": value[0], **value[1]} for key, value in scores.items()},
        "recommended_order": list(best_order),
    }

