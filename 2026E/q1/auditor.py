"""基于最新静态场景审查上次动作和全部模板状态。"""

from __future__ import annotations

import numpy as np

from .models import AuditResult, PieceTaskStatus, SceneAnalysis, SingleMovePlan


def _point_in_rect(point: np.ndarray, origin_mm: tuple[float, float], width: float = 100.0, height: float = 60.0) -> bool:
    x, y = float(point[0]), float(point[1])
    return origin_mm[0] <= x <= origin_mm[0] + width and origin_mm[1] <= y <= origin_mm[1] + height


def _near(a: np.ndarray, b: np.ndarray, tol_mm: float) -> bool:
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b))) <= tol_mm


def audit_scene(
    scene: SceneAnalysis,
    previous_action: SingleMovePlan | None,
    previous_scene: SceneAnalysis | None,
    *,
    remaining_move_tolerance_mm: float = 3.0,
    target_origin_mm: tuple[float, float] = (55.0, 168.5),
) -> AuditResult:
    placed_ok = {key for key, state in scene.templates.items() if state.status == PieceTaskStatus.PLACED_OK}
    placed_offset = {key for key, state in scene.templates.items() if state.status == PieceTaskStatus.PLACED_OFFSET}
    remaining = {key for key, state in scene.templates.items() if state.status == PieceTaskStatus.UNPLACED}
    missing = {key for key, state in scene.templates.items() if state.status == PieceTaskStatus.MISSING}
    moved: set[str] = set()
    warnings = list(scene.warnings)

    if previous_scene is not None:
        for template_id in remaining:
            old = previous_scene.templates.get(template_id)
            new = scene.templates.get(template_id)
            if old and new and old.detected_piece and new.detected_piece:
                distance = np.linalg.norm(
                    np.asarray(new.detected_piece.center_mm) - np.asarray(old.detected_piece.center_mm)
                )
                if distance > remaining_move_tolerance_mm:
                    moved.add(template_id)
                    warnings.append(f"{template_id}源位姿移动{distance:.2f}mm，已使用最新场景")

    pick_failed = None
    release_failed = None
    dropped = None
    temporarily_missing = None
    recovery_template = None
    recovery_mode = None

    if previous_action is not None:
        tid = previous_action.template_id
        state = scene.templates.get(tid)
        prev_state = previous_scene.templates.get(tid) if previous_scene else None
        source_ref = (
            np.asarray(previous_action.pick_point_source_mm)
            if previous_action.pick_point_source_mm is not None
            else np.asarray(previous_action.pick_point_paper)
        )
        release_ref = (
            np.asarray(previous_action.release_point_target_mm)
            if previous_action.release_point_target_mm is not None
            else np.asarray(
                [previous_action.target_pose_paper.x_mm, previous_action.target_pose_paper.y_mm]
            )
        )

        if state is not None and state.detected_piece is not None:
            center = np.asarray(state.detected_piece.center_mm)
            if state.status == PieceTaskStatus.UNPLACED and _near(center, source_ref, 15.0):
                pick_failed = tid
                state.status = PieceTaskStatus.PICK_FAILED
                warnings.append(f"{tid}: PICK_FAILED（仍在源附近）")
            elif state.status == PieceTaskStatus.PLACED_OFFSET:
                warnings.append(f"{tid}: PLACED_OFFSET")
            elif state.status == PieceTaskStatus.PLACED_OK:
                pass
            elif not _point_in_rect(center, target_origin_mm) and not _near(center, source_ref, 20.0):
                dropped = tid
                state.status = PieceTaskStatus.DROPPED_DURING_TRANSFER
                warnings.append(f"{tid}: DROPPED_DURING_TRANSFER")
            elif state.status == PieceTaskStatus.UNPLACED and not _near(center, source_ref, 15.0):
                # 离开源区但未正确放置
                if _point_in_rect(center, target_origin_mm):
                    state.status = PieceTaskStatus.PLACED_OFFSET
                    placed_offset.add(tid)
                    remaining.discard(tid)
                else:
                    dropped = tid
                    state.status = PieceTaskStatus.DROPPED_DURING_TRANSFER
        elif state is None or state.status == PieceTaskStatus.MISSING or state.detected_piece is None:
            # 源与目标都找不到：释放失败或临时丢失；不得从虚构源重规划
            temporarily_missing = tid
            release_failed = tid
            recovery_template = tid
            recovery_mode = "RELEASE_RECOVERY_FROM_LAST_PLAN"
            if state is not None:
                state.status = PieceTaskStatus.PIECE_TEMPORARILY_MISSING
                state.recovery_hint = recovery_mode
            warnings.append(f"{tid}: RELEASE_FAILED/PIECE_TEMPORARILY_MISSING，使用上一轮计划恢复")
            missing.add(tid)

        # 身份不确定
        if scene.assignment_margin is not None and scene.assignment_margin < 0.35 and not scene.scene_valid:
            warnings.append("PIECE_IDENTITY_AMBIGUOUS")

    all_complete = scene.scene_valid and len(placed_ok) == 4 and not placed_offset and not missing
    return AuditResult(
        all_complete=all_complete,
        placed_ok=placed_ok,
        placed_offset=placed_offset,
        remaining=remaining,
        moved_remaining=moved,
        release_failed_template=release_failed,
        missing_templates=missing,
        requires_reanalysis=not scene.scene_valid and recovery_mode is None,
        warnings=warnings,
        pick_failed_template=pick_failed,
        dropped_template=dropped,
        temporarily_missing_template=temporarily_missing,
        recovery_template=recovery_template,
        recovery_mode=recovery_mode,
    )
