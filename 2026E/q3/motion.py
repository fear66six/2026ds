"""Convert a solved card assembly into the completed Q1 motion contract."""

from __future__ import annotations

import math

import numpy as np

from q1.calibration import ArmCoordinateMapper, contact_height_mm
from q1.geometry import (
    apply_uniform_shared_edge_gap,
    apply_rigid_transform,
    compute_rigid_transform,
    polygon_maximum_clearance_point,
)
from q1.models import PaperPose, PieceMove, RobotPose, SingleMovePlan
from q1.wrist import (
    normalize_angle_deg,
    smaller_azimuth_angle_deg,
    swing_roll_compensation_deg,
)

from .card_solver.geometry import Point, RigidTransform, normalize_angle
from .card_solver.models import CardPuzzleInput, Solution
from .runtime_config import Q3RuntimeConfig


def target_global_transform(
    puzzle: CardPuzzleInput,
    solution: Solution,
) -> RigidTransform:
    """Place the solved card upright at the centre of the destination half."""

    if solution.rectangle is None:
        raise RuntimeError("CARD_SOLUTION_HAS_NO_RECTANGLE")
    coordinates = list(solution.rectangle.exterior.coords)[:-1]
    edges = [
        (
            math.dist(coordinates[index], coordinates[(index + 1) % 4]),
            coordinates[index],
            coordinates[(index + 1) % 4],
        )
        for index in range(4)
    ]
    _, first, second = max(edges, key=lambda item: item[0])
    long_angle = math.atan2(second[1] - first[1], second[0] - first[0])
    rotation = normalize_angle(math.pi / 2.0 - long_angle)
    rotation_transform = RigidTransform(rotation)
    transformed = [
        rotation_transform.apply(Point(float(x), float(y)))
        for x, y in coordinates
    ]
    centre_x = 0.5 * (
        min(point.x for point in transformed) + max(point.x for point in transformed)
    )
    centre_y = 0.5 * (
        min(point.y for point in transformed) + max(point.y for point in transformed)
    )
    paper_width, paper_height = puzzle.paper_size_mm
    if puzzle.layout == "left-right":
        target_centre = Point(
            0.5 * (puzzle.divider_mm + paper_width),
            paper_height / 2.0,
        )
    else:
        target_centre = Point(
            paper_width / 2.0,
            0.5 * (puzzle.divider_mm + paper_height),
        )
    return RigidTransform(
        rotation,
        (target_centre.x - centre_x, target_centre.y - centre_y),
    )


def _portrait_paper_points(
    points: np.ndarray,
    paper_size_mm: tuple[float, float],
) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if paper_size_mm[0] > paper_size_mm[1]:
        return values[:, [1, 0]]
    return values


def _build_move(
    *,
    cycle_index: int,
    piece_id: int,
    source_vertices_mm: np.ndarray,
    target_vertices_mm: np.ndarray,
    mapper: ArmCoordinateMapper,
    config: Q3RuntimeConfig,
    confidence: float,
) -> SingleMovePlan:
    transform = compute_rigid_transform(source_vertices_mm, target_vertices_mm)
    if not transform.valid or transform.max_error_mm > float(config.vertex_max_error_mm):
        raise RuntimeError(
            "CARD_PLAN_GEOMETRY_RESIDUAL: "
            f"piece={piece_id}, max_error_mm={transform.max_error_mm:.3f}"
        )

    pick_point_source_mm = polygon_maximum_clearance_point(source_vertices_mm)
    release_point_target_mm = apply_rigid_transform(pick_point_source_mm, transform)
    rotation_delta_deg = float(transform.rotation_deg)
    source = PaperPose(
        float(pick_point_source_mm[0]),
        float(pick_point_source_mm[1]),
        0.0,
    )
    target = PaperPose(
        float(release_point_target_mm[0]),
        float(release_point_target_mm[1]),
        rotation_delta_deg,
    )

    if config.pick_height is None:
        raise RuntimeError("CALIBRATION_REQUIRED: missing pick height")
    low_z = contact_height_mm(config.pick_height)
    source_robot = mapper.paper_to_robot(
        source.x_mm,
        source.y_mm,
        low_z,
        roll_deg=0.0,
    )
    source_robot.x += float(config.pick_robot_xy_offset_mm[0])
    source_robot.y += float(config.pick_robot_xy_offset_mm[1])
    target_robot = mapper.paper_to_robot(
        target.x_mm,
        target.y_mm,
        low_z,
        roll_deg=0.0,
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
    if not mapper.wrist_mapping_ready():
        raise RuntimeError(
            "CALIBRATION_REQUIRED: missing wrist roll zero/sign calibration"
        )
    signed_motion_deg = float(mapper.wrist_roll_sign) * rotation_delta_deg
    motion_candidates = [signed_motion_deg]
    if abs(signed_motion_deg) > 1e-9:
        motion_candidates.append(
            signed_motion_deg - np.copysign(360.0, signed_motion_deg)
        )
    roll_candidates: list[tuple[float, float, float, float]] = []
    for motion_deg in motion_candidates:
        commanded_motion_deg = motion_deg + swing_compensation_deg
        if abs(commanded_motion_deg) <= 1e-9:
            candidate_pick_roll = float(mapper.wrist_roll_zero_deg)
        else:
            candidate_pick_roll = -90.0 if commanded_motion_deg > 0.0 else 90.0
        candidate_geometric_release = candidate_pick_roll + motion_deg
        candidate_release = candidate_geometric_release + swing_compensation_deg
        if -90.0 <= candidate_release <= 90.0:
            roll_candidates.append(
                (
                    abs(commanded_motion_deg),
                    candidate_pick_roll,
                    candidate_geometric_release,
                    candidate_release,
                )
            )
    if not roll_candidates:
        raise RuntimeError(
            "CARD_PLAN_ROLL_OUT_OF_RANGE: no equivalent wrist rotation stays "
            "inside [-90, 90] after swing compensation; "
            f"piece={piece_id}, rotation_delta_deg={rotation_delta_deg:.3f}, "
            f"swing_compensation_deg={swing_compensation_deg:.3f}"
        )
    (
        _,
        pick_roll_deg,
        geometric_release_roll_deg,
        release_roll_deg,
    ) = min(roll_candidates, key=lambda candidate: candidate[0])
    source_robot.roll = pick_roll_deg
    target_robot.roll = release_roll_deg
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
    roll_delta_deg = normalize_angle_deg(release_roll_deg - pick_roll_deg)
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
    transfer_pose = RobotPose(
        target_robot.x,
        target_robot.y,
        float(config.transfer_transit_z),
        target_robot.pitch,
        release_roll_deg,
        target_robot.claw,
        int(config.transfer_move_duration_ms),
    )

    return SingleMovePlan(
        cycle_index=cycle_index,
        template_id=f"CARD_{piece_id + 1}",
        source_pose_paper=source,
        target_pose_paper=target,
        source_pose_robot=source_robot,
        target_pose_robot=target_robot,
        pick_point_paper=(source.x_mm, source.y_mm),
        pick_point_robot=source_robot,
        approach_pose=approach,
        transfer_pose=transfer_pose,
        release_pose=target_robot,
        rotation_delta_deg=rotation_delta_deg,
        confidence=confidence,
        reason_selected="CARD_PATTERN_GLOBAL_SOLUTION",
        retry_index=0,
        source_vertices_mm=source_vertices_mm,
        target_vertices_mm=target_vertices_mm,
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


def plan_card_moves(
    puzzle: CardPuzzleInput,
    solution: Solution,
    mapper: ArmCoordinateMapper,
    config: Q3RuntimeConfig,
) -> list[PieceMove]:
    if not solution.success:
        raise RuntimeError(f"CARD_SOLVE_FAILED: {solution.reason}")
    observations = {item.piece.id: item for item in puzzle.observations}
    global_transform = target_global_transform(puzzle, solution)
    placed_items = sorted(
        solution.placed_pieces,
        key=lambda item: observations[item.piece_id].piece.area,
        reverse=True,
    )
    source_vertices_by_id: dict[int, np.ndarray] = {}
    target_vertices_by_id: dict[int, np.ndarray] = {}
    for placed in placed_items:
        observation = observations[placed.piece_id]
        final_transform = global_transform.compose(placed.transform)
        source_board = np.asarray(
            [point.as_tuple() for point in observation.piece.vertices],
            dtype=np.float64,
        )
        target_board = np.asarray(
            [final_transform.apply(point).as_tuple() for point in observation.piece.vertices],
            dtype=np.float64,
        )
        source_vertices_by_id[placed.piece_id] = _portrait_paper_points(
            source_board,
            puzzle.paper_size_mm,
        )
        target_vertices_by_id[placed.piece_id] = _portrait_paper_points(
            target_board,
            puzzle.paper_size_mm,
        )
    if config.edge_gap_enabled:
        target_vertices_by_id = apply_uniform_shared_edge_gap(
            target_vertices_by_id,
            config.edge_gap_mm,
            shared_edge_pairs=(
                (
                    seam.first_piece_id,
                    seam.first_edge_id,
                    seam.second_piece_id,
                    seam.second_edge_id,
                )
                for seam in solution.seams
                if seam.first_piece_id >= 0 and seam.second_piece_id >= 0
            ),
        )

    confidence = float(solution.pattern_confidence or 0.0)
    moves: list[PieceMove] = []
    for placed in placed_items:
        moves.append(
            _build_move(
                cycle_index=len(moves),
                piece_id=placed.piece_id,
                source_vertices_mm=source_vertices_by_id[placed.piece_id],
                target_vertices_mm=target_vertices_by_id[placed.piece_id],
                mapper=mapper,
                config=config,
                confidence=confidence,
            )
        )
    return moves
