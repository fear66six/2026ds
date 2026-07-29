"""基于最新场景只规划一块；缺少标定时不生成机械臂坐标。"""

from __future__ import annotations

import numpy as np

from .calibration import ArmCoordinateMapper
from .geometry import normalize_angle_deg
from .models import PaperPose, SceneAnalysis, SingleMovePlan
from .runtime_config import Q1RuntimeConfig


def plan_single_move(
    scene: SceneAnalysis,
    template_id: str,
    mapper: ArmCoordinateMapper,
    config: Q1RuntimeConfig,
    *,
    reason_selected: str,
) -> SingleMovePlan:
    state = scene.templates[template_id]
    piece = state.detected_piece
    if piece is None:
        raise RuntimeError(f"PLAN_FAILED: {template_id}当前不可见")
    source = PaperPose(piece.center_mm[0], piece.center_mm[1], piece.angle_deg)
    target_center = np.mean(state.expected_target_vertices_mm, axis=0)
    target = PaperPose(float(target_center[0]), float(target_center[1]), 0.0)

    source_robot = target_robot = pick_robot = approach = transfer = release = None
    if mapper.is_calibrated():
        if None in (config.pick_height, config.release_height, config.safe_height, config.move_duration_ms):
            raise RuntimeError("CALIBRATION_REQUIRED: 缺少抓取/释放/安全高度或动作时间")
        source_robot = mapper.paper_to_robot(source.x_mm, source.y_mm, float(config.pick_height))
        target_robot = mapper.paper_to_robot(target.x_mm, target.y_mm, float(config.release_height))
        pick_robot = source_robot
        approach = mapper.paper_to_robot(source.x_mm, source.y_mm, float(config.safe_height))
        transfer = mapper.paper_to_robot(target.x_mm, target.y_mm, float(config.safe_height))
        release = target_robot
        for pose in (source_robot, target_robot, pick_robot, approach, transfer, release):
            pose.duration_ms = int(config.move_duration_ms)

    return SingleMovePlan(
        cycle_index=scene.cycle_index,
        template_id=template_id,
        source_pose_paper=source,
        target_pose_paper=target,
        source_pose_robot=source_robot,
        target_pose_robot=target_robot,
        pick_point_paper=piece.center_mm,
        pick_point_robot=pick_robot,
        approach_pose=approach,
        transfer_pose=transfer,
        release_pose=release,
        rotation_delta_deg=normalize_angle_deg(-piece.angle_deg),
        confidence=piece.confidence,
        reason_selected=reason_selected,
        retry_index=state.retry_count,
    )
