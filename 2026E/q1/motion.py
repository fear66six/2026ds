"""基于最新场景只规划一块；使用完整 R、t 与区分 pick/release roll。"""

from __future__ import annotations

import numpy as np

from .calibration import ArmCoordinateMapper
from .config import DIVIDER_Y_CM
from .geometry import apply_rigid_transform, compute_rigid_transform, normalize_angle_deg
from .models import PaperPose, SceneAnalysis, SingleMovePlan
from .runtime_config import Q1RuntimeConfig


def _validate_pose_workspace(pose, config: Q1RuntimeConfig) -> None:
    limits = config.workspace_limits or {}
    for axis in ("x", "y", "z", "pitch", "roll", "claw"):
        value = float(getattr(pose, axis))
        if axis not in limits or not limits[axis][0] <= value <= limits[axis][1]:
            raise RuntimeError(
                f"PLAN_OUT_OF_WORKSPACE: {axis}={value}, limits={limits.get(axis)}"
            )


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
    if (
        piece.region != "UPPER_SOURCE"
        or float(piece.center_mm[1]) >= DIVIDER_Y_CM * 10.0
    ):
        raise RuntimeError(
            "PLAN_FAILED: source piece is not in the detected source half; "
            f"template={template_id}, region={piece.region}, center_mm={piece.center_mm}"
        )
    source_vertices = np.asarray(piece.vertices_mm, dtype=np.float64)
    target_vertices = np.asarray(state.expected_target_vertices_mm, dtype=np.float64)
    transform = compute_rigid_transform(source_vertices, target_vertices)
    if not transform.valid:
        raise RuntimeError(f"PLAN_FAILED: {template_id}刚性变换无效: {transform.rejection_reason}")
    if transform.max_error_mm > float(config.vertex_max_error_mm):
        raise RuntimeError(
            "PLAN_GEOMETRY_RESIDUAL: no arm motion sent; "
            f"template={template_id}, max_error_mm={transform.max_error_mm:.3f}, "
            f"rms_error_mm={transform.rms_error_mm:.3f}, "
            f"limit_mm={float(config.vertex_max_error_mm):.3f}"
        )

    pick_point_source_mm = np.asarray(piece.center_mm, dtype=np.float64)
    release_point_target_mm = apply_rigid_transform(pick_point_source_mm, transform)
    rotation_delta_deg = normalize_angle_deg(transform.rotation_deg)

    source = PaperPose(float(pick_point_source_mm[0]), float(pick_point_source_mm[1]), piece.angle_deg)
    target = PaperPose(float(release_point_target_mm[0]), float(release_point_target_mm[1]), 0.0)
    if target.y_mm < DIVIDER_Y_CM * 10.0:
        raise RuntimeError(
            "PLAN_FAILED: release target is not in the target half; "
            f"template={template_id}, target_mm=({target.x_mm}, {target.y_mm})"
        )

    source_robot = target_robot = pick_robot = release = None
    approach = transfer = rotate_pose = None
    pick_roll_deg = release_roll_deg = None
    if mapper.is_calibrated():
        if None in (config.pick_height, config.release_height, config.move_duration_ms):
            raise RuntimeError("CALIBRATION_REQUIRED: 缺少抓取/释放高度或动作时间")
        wrist = mapper.map_in_plane_rotation(rotation_delta_deg)
        if not wrist.valid:
            raise RuntimeError(wrist.rejection_reason or "WRIST_ROTATION_OUT_OF_RANGE")
        pick_roll_deg = float(wrist.pick_roll_deg)
        release_roll_deg = float(wrist.release_roll_deg)

        source_robot = mapper.paper_to_robot(source.x_mm, source.y_mm, float(config.pick_height), roll_deg=pick_roll_deg)
        pick_robot = source_robot
        target_robot = mapper.paper_to_robot(
            target.x_mm, target.y_mm, float(config.release_height), roll_deg=release_roll_deg
        )
        release = target_robot
        for pose in (source_robot, target_robot, pick_robot, release):
            pose.duration_ms = int(config.move_duration_ms)
            _validate_pose_workspace(pose, config)

    return SingleMovePlan(
        cycle_index=scene.cycle_index,
        template_id=template_id,
        source_pose_paper=source,
        target_pose_paper=target,
        source_pose_robot=source_robot,
        target_pose_robot=target_robot,
        pick_point_paper=(float(pick_point_source_mm[0]), float(pick_point_source_mm[1])),
        pick_point_robot=pick_robot,
        approach_pose=approach,
        transfer_pose=transfer,
        release_pose=release,
        rotation_delta_deg=float(rotation_delta_deg),
        confidence=piece.confidence,
        reason_selected=reason_selected,
        retry_index=state.retry_count,
        source_vertices_mm=source_vertices,
        target_vertices_mm=target_vertices,
        rigid_transform=transform,
        pick_point_source_mm=pick_point_source_mm,
        release_point_target_mm=release_point_target_mm,
        pick_roll_deg=pick_roll_deg,
        release_roll_deg=release_roll_deg,
        rotate_pose=rotate_pose,
    )
