"""基于最新静态场景审查上次动作和全部模板状态。"""

from __future__ import annotations

import numpy as np

from .models import AuditResult, PieceTaskStatus, SceneAnalysis, SingleMovePlan


def audit_scene(
    scene: SceneAnalysis,
    previous_action: SingleMovePlan | None,
    previous_scene: SceneAnalysis | None,
    *,
    remaining_move_tolerance_mm: float = 3.0,
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

    release_failed = None
    if previous_action is not None:
        state = scene.templates.get(previous_action.template_id)
        if state is None or state.status in (PieceTaskStatus.UNPLACED, PieceTaskStatus.MISSING):
            release_failed = previous_action.template_id
            warnings.append(f"{previous_action.template_id}未在目标区确认释放")

    all_complete = (
        scene.scene_valid
        and len(placed_ok) == 4
        and not placed_offset
        and not missing
    )
    return AuditResult(
        all_complete=all_complete,
        placed_ok=placed_ok,
        placed_offset=placed_offset,
        remaining=remaining,
        moved_remaining=moved,
        release_failed_template=release_failed,
        missing_templates=missing,
        requires_reanalysis=not scene.scene_valid,
        warnings=warnings,
    )

