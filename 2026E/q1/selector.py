"""动态下一块选择；每轮只返回一个模板。真实几何评分，禁止固定占位。"""

from __future__ import annotations

import itertools
import math

import numpy as np

from . import config
from .models import AuditResult, PieceTaskStatus, SceneAnalysis
from .pieces import target_rectangle_vertices_mm


def _segment_clearance_mm(path_a: np.ndarray, path_b: np.ndarray, obstacle: np.ndarray) -> float:
    """路径段到障碍多边形的近似最小距离。"""
    pts = np.asarray(obstacle, dtype=np.float64).reshape(-1, 2)
    a = np.asarray(path_a, dtype=np.float64)
    b = np.asarray(path_b, dtype=np.float64)
    ab = b - a
    length = float(np.linalg.norm(ab))
    if length < 1e-9:
        return float(np.min(np.linalg.norm(pts - a, axis=1)))
    samples = a + np.linspace(0.0, 1.0, 8)[:, None] * ab
    # 到障碍顶点/边的距离下界：用到顶点距离近似
    return float(np.min(np.linalg.norm(samples[:, None, :] - pts[None, :, :], axis=2)))


def _release_clearance(target_center: np.ndarray, occupied: list[np.ndarray], origin_mm: tuple[float, float]) -> float:
    directions = {
        "LEFT": np.array([-1.0, 0.0]),
        "RIGHT": np.array([1.0, 0.0]),
        "UP": np.array([0.0, -1.0]),
        "DOWN": np.array([0.0, 1.0]),
    }
    rect = target_rectangle_vertices_mm(origin_mm)
    free = 0
    for delta in directions.values():
        probe = target_center + delta * config.RELEASE_PEEL_DISTANCE_MM
        if probe[0] < 0 or probe[0] > 210 or probe[1] < 0 or probe[1] > 297:
            continue
        blocked = False
        for poly in occupied:
            if _segment_clearance_mm(target_center, probe, poly) < config.TOOL_RADIUS_MM:
                blocked = True
                break
        # 是否越出目标框过多
        if probe[0] < rect[:, 0].min() - 5 or probe[0] > rect[:, 0].max() + 5:
            pass
        if not blocked:
            free += 1
    return free / 4.0


def _path_collision_risk(
    source: np.ndarray,
    target: np.ndarray,
    obstacles: list[np.ndarray],
) -> float:
    radius = config.TOOL_RADIUS_MM + config.TOOL_CLEARANCE_MARGIN_MM
    hits = 0
    for poly in obstacles:
        if _segment_clearance_mm(source, target, poly) < radius:
            hits += 1
    if not obstacles:
        return 0.0
    return min(1.0, hits / max(len(obstacles), 1))


def _blocking_future_targets(
    scene: SceneAnalysis,
    template_id: str,
    remaining: list[str],
) -> float:
    state = scene.templates[template_id]
    target = np.asarray(state.expected_target_vertices_mm, dtype=np.float64)
    expand = config.TOOL_RADIUS_MM + config.TOOL_CLEARANCE_MARGIN_MM
    center = target.mean(axis=0)
    blocked = 0
    considered = 0
    for other_id in remaining:
        if other_id == template_id:
            continue
        considered += 1
        other = scene.templates[other_id].expected_target_vertices_mm
        other_c = np.mean(other, axis=0)
        dist = float(np.linalg.norm(center - other_c))
        # 目标膨胀后是否显著侵入后续目标中心邻域
        if dist < expand + 15.0:
            blocked += 1
    if considered == 0:
        return 0.0
    return blocked / considered


def _verification_visibility(scene: SceneAnalysis, template_id: str) -> float:
    state = scene.templates[template_id]
    target = np.asarray(state.expected_target_vertices_mm, dtype=np.float64)
    center = target.mean(axis=0)
    origin = target.min(axis=0)
    # 靠外框/接缝更易观察
    border = float(
        min(
            center[0] - origin[0],
            origin[0] + 100.0 - center[0],
            center[1] - origin[1],
            origin[1] + 60.0 - center[1],
        )
    )
    # 越小越靠边，可见性越高
    return float(np.clip(1.0 - border / 40.0, 0.0, 1.0))


def _candidate_score(scene: SceneAnalysis, template_id: str, remaining: list[str]) -> tuple[float, dict[str, float]]:
    state = scene.templates[template_id]
    piece = state.detected_piece
    if piece is None:
        return -math.inf, {"missing": 1.0}
    target_center = np.mean(state.expected_target_vertices_mm, axis=0)
    source = np.asarray(piece.center_mm)
    move_distance = float(np.linalg.norm(target_center - source))
    required_rotation = abs(float(getattr(state, "angle_error_deg", None) or piece.angle_deg))

    occupied = [
        np.asarray(scene.templates[tid].expected_target_vertices_mm)
        for tid in scene.placed_templates
        if scene.templates[tid].detected_piece is not None
    ]
    obstacles = []
    for tid, other in scene.templates.items():
        if tid == template_id or other.detected_piece is None:
            continue
        if other.status == PieceTaskStatus.UNPLACED:
            obstacles.append(np.asarray(other.detected_piece.vertices_mm))
        elif other.status == PieceTaskStatus.PLACED_OK:
            obstacles.append(np.asarray(other.detected_piece.vertices_mm))

    path_risk = _path_collision_risk(source, target_center, obstacles)
    blocking = _blocking_future_targets(scene, template_id, remaining)
    origin = (
        float(np.min(scene.templates["P1"].expected_target_vertices_mm[:, 0])),
        float(np.min(scene.templates["P1"].expected_target_vertices_mm[:, 1])),
    )
    release_clear = _release_clearance(target_center, occupied, origin)
    visibility = _verification_visibility(scene, template_id)
    clearance = float(min(target_center[0], 210.0 - target_center[0], target_center[1], 297.0 - target_center[1]))

    features = {
        "template_match_confidence": float(piece.confidence),
        "edge_fit_confidence": float(max(0.0, 1.0 - piece.edge_fit_rmse_mm / 5.0)),
        "target_pose_confidence": float(max(0.0, 1.0 - (state.max_vertex_error_mm or 20.0) / 20.0)),
        "target_clearance": clearance,
        "release_clearance": release_clear,
        "tool_clearance": float(max(0.0, 1.0 - path_risk)),
        "path_collision_risk": path_risk,
        "blocking_future_targets": blocking,
        "verification_visibility": visibility,
        "source_pick_accessibility": float(min(1.0, piece.area_mm2 / 1000.0)),
        "required_rotation": required_rotation,
        "move_distance": move_distance,
    }
    score = (
        4.0 * features["template_match_confidence"]
        + 1.5 * features["edge_fit_confidence"]
        + 1.0 * features["target_pose_confidence"]
        + 0.02 * clearance
        + 1.2 * release_clear
        + 1.0 * features["tool_clearance"]
        + 1.5 * visibility
        + features["source_pick_accessibility"]
        - 2.5 * path_risk
        - 2.0 * blocking
        - 0.003 * move_distance
        - 0.003 * required_rotation
    )
    return score, features


def select_next_piece(scene: SceneAnalysis, audit: AuditResult) -> tuple[str, dict]:
    if audit.recovery_template and audit.recovery_mode:
        return audit.recovery_template, {
            "reason": audit.recovery_mode,
            "priority": 0,
            "use_previous_plan": True,
        }
    if audit.pick_failed_template:
        return audit.pick_failed_template, {"reason": "PICK_FAILED_RETRY", "priority": 1}
    if audit.dropped_template:
        return audit.dropped_template, {"reason": "DROPPED_RECOVERY", "priority": 1}
    if audit.release_failed_template:
        return audit.release_failed_template, {
            "reason": "RELEASE_UNCONFIRMED",
            "priority": 1,
            "use_previous_plan": True,
        }
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

    scores = {key: _candidate_score(scene, key, candidates) for key in candidates}
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
