"""从一次桌面识别结果生成有序 PieceMove 队列。"""

from __future__ import annotations

import numpy as np

from .calibration import ArmCoordinateMapper
from .config import DIVIDER_Y_CM
from .geometry import (
    apply_rigid_transform,
    compute_rigid_transform,
    normalize_angle_deg,
    polygon_maximum_clearance_point,
)
from .models import (
    PaperPose,
    PieceMove,
    PieceTaskStatus,
    RobotPose,
    SceneAnalysis,
    SingleMovePlan,
)
from .puzzle_solver import TEMPLATE_IDS
from .runtime_config import Q1RuntimeConfig
from .wrist import (
    normalize_angle_deg as normalize_roll_command_deg,
    smaller_azimuth_angle_deg,
    swing_roll_compensation_deg,
)


PLACE_ORDER = ("P4", "P3", "P2", "P1")


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

    pick_point_source_mm = polygon_maximum_clearance_point(piece.vertices_mm)
    release_point_target_mm = apply_rigid_transform(pick_point_source_mm, transform)
    rotation_delta_deg = normalize_angle_deg(transform.rotation_deg)

    source = PaperPose(
        float(pick_point_source_mm[0]),
        float(pick_point_source_mm[1]),
        piece.angle_deg,
    )
    target = PaperPose(float(release_point_target_mm[0]), float(release_point_target_mm[1]), 0.0)
    if target.y_mm < DIVIDER_Y_CM * 10.0:
        raise RuntimeError(
            "PLAN_FAILED: release target is not in the target half; "
            f"template={template_id}, target_mm=({target.x_mm}, {target.y_mm})"
        )

    source_robot = target_robot = pick_robot = release = None
    approach = transfer = rotate_pose = None
    pick_roll_deg = release_roll_deg = None
    geometric_release_roll_deg = swing_azimuth_deg = swing_compensation_deg = None
    if mapper.is_calibrated():
        if None in (
            config.pick_height,
            config.release_height,
            config.transfer_transit_z,
            config.transfer_move_duration_ms,
        ):
            raise RuntimeError("CALIBRATION_REQUIRED: 缺少抓取/释放高度或 transfer 参数")
        wrist = mapper.map_in_plane_rotation(rotation_delta_deg)
        pick_roll_deg = float(wrist.pick_roll_deg)
        geometric_release_roll_deg = float(wrist.release_roll_deg)

        source_robot = mapper.paper_to_robot(
            source.x_mm,
            source.y_mm,
            float(config.pick_height),
            roll_deg=pick_roll_deg,
        )
        source_robot.x += float(config.pick_robot_xy_offset_mm[0])
        source_robot.y += float(config.pick_robot_xy_offset_mm[1])
        pick_robot = source_robot
        target_robot = mapper.paper_to_robot(
            target.x_mm,
            target.y_mm,
            float(config.release_height),
            roll_deg=geometric_release_roll_deg,
        )
        swing_azimuth_deg = smaller_azimuth_angle_deg(
            source_robot.x,
            source_robot.y,
            target_robot.x,
            target_robot.y,
        )
        swing_compensation_deg = 0.0
        if config.swing_roll_compensate:
            swing_compensation_deg = swing_roll_compensation_deg(
                (source_robot.x, source_robot.y),
                (target_robot.x, target_robot.y),
                sign=float(config.swing_roll_sign),
            )
        release_roll_deg = normalize_roll_command_deg(
            geometric_release_roll_deg + swing_compensation_deg
        )
        target_robot.roll = release_roll_deg
        release = target_robot
        source_robot.duration_ms = int(config.transfer_descend_duration_ms)
        target_robot.duration_ms = int(config.transfer_descend_duration_ms)

        approach = RobotPose(
            source_robot.x,
            source_robot.y,
            source_robot.z + float(config.transfer_approach_dz_mm),
            source_robot.pitch,
            source_robot.roll,
            source_robot.claw,
            int(config.transfer_move_duration_ms),
        )
        roll_delta_deg = normalize_roll_command_deg(
            release_roll_deg - pick_roll_deg
        )
        rotate_duration_ms = max(
            400,
            int(
                int(config.transfer_rotate_duration_ms)
                * max(0.5, abs(roll_delta_deg) / 90.0)
            ),
        )
        rotate_pose = RobotPose(
            source_robot.x,
            source_robot.y,
            float(config.transfer_transit_z),
            target_robot.pitch,
            release_roll_deg,
            source_robot.claw,
            rotate_duration_ms,
        )
        transfer = RobotPose(
            target_robot.x,
            target_robot.y,
            float(config.transfer_transit_z),
            target_robot.pitch,
            release_roll_deg,
            target_robot.claw,
            int(config.transfer_move_duration_ms),
        )

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
        geometric_release_roll_deg=geometric_release_roll_deg,
        swing_azimuth_deg=swing_azimuth_deg,
        swing_roll_compensation_deg=swing_compensation_deg,
        rotate_pose=rotate_pose,
    )


def plan_piece_moves(
    scene: SceneAnalysis,
    mapper: ArmCoordinateMapper,
    config: Q1RuntimeConfig,
) -> list[PieceMove]:
    """Build one large-to-small queue from the single initial observation."""
    if not scene.scene_valid:
        raise RuntimeError("PLAN_FAILED: initial scene is invalid")

    moves: list[PieceMove] = []
    for template_id in PLACE_ORDER:
        state = scene.templates.get(template_id)
        if state is None:
            raise RuntimeError(f"PLAN_FAILED: missing template state {template_id}")
        if state.status == PieceTaskStatus.PLACED_OK:
            continue
        if (
            state.status != PieceTaskStatus.UNPLACED
            or state.detected_piece is None
            or state.detected_piece.region != "UPPER_SOURCE"
        ):
            raise RuntimeError(
                "PLAN_FAILED: every pending piece must start in the source half; "
                f"template={template_id}, status={state.status.value}, "
                f"region={getattr(state.detected_piece, 'region', None)}"
            )

        move = plan_single_move(
            scene,
            template_id,
            mapper,
            config,
            reason_selected="INITIAL_SCENE_LARGE_TO_SMALL_QUEUE",
        )
        move.cycle_index = len(moves)
        moves.append(move)
    return moves
