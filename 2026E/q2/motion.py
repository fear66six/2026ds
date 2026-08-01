"""Convert an exact Q2 rectangle solution into the Q1 motion contract."""

from __future__ import annotations

import math

import numpy as np

from q1.calibration import ArmCoordinateMapper
from q1.geometry import (
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

from .analyzer import is_executable_solution
from .puzzle_solver.geometry import normalize_angle
from .puzzle_solver.image_input import ImagePuzzleInput
from .puzzle_solver.models import PlacedPiece, Solution
from .runtime_config import Q2RuntimeConfig


def target_solution_vertices(
    puzzle: ImagePuzzleInput,
    solution: Solution,
) -> dict[int, np.ndarray]:
    """Orient the solved long side horizontally and centre it below the divider."""

    if solution.rectangle is None or puzzle.divider_y_mm is None:
        raise RuntimeError("Q2_SOLUTION_TARGET_GEOMETRY_MISSING")
    rectangle = list(solution.rectangle.exterior.coords)[:-1]
    edges = [
        (
            math.dist(rectangle[index], rectangle[(index + 1) % 4]),
            rectangle[index],
            rectangle[(index + 1) % 4],
        )
        for index in range(4)
    ]
    _, first, second = max(edges, key=lambda item: item[0])
    rotation = normalize_angle(-math.atan2(second[1] - first[1], second[0] - first[0]))
    cos_angle = math.cos(rotation)
    sin_angle = math.sin(rotation)
    matrix = np.asarray(
        ((cos_angle, -sin_angle), (sin_angle, cos_angle)),
        dtype=np.float64,
    )

    rotated: dict[int, np.ndarray] = {}
    all_vertices: list[np.ndarray] = []
    for placed in solution.placed_pieces:
        vertices = np.asarray(
            [point.as_tuple() for point in placed.vertices],
            dtype=np.float64,
        )
        transformed = vertices @ matrix.T
        rotated[placed.piece_id] = transformed
        all_vertices.append(transformed)

    combined = np.vstack(all_vertices)
    current_center = 0.5 * (combined.min(axis=0) + combined.max(axis=0))
    paper_width, paper_height = puzzle.paper_size_mm
    target_center = np.asarray(
        (
            paper_width / 2.0,
            puzzle.divider_y_mm + (paper_height - puzzle.divider_y_mm) / 2.0,
        ),
        dtype=np.float64,
    )
    translation = target_center - current_center
    targets = {
        piece_id: vertices + translation
        for piece_id, vertices in rotated.items()
    }
    target_union = np.vstack(list(targets.values()))
    if (
        target_union[:, 0].min() < 0.0
        or target_union[:, 0].max() > paper_width
        or target_union[:, 1].min() <= puzzle.divider_y_mm
        or target_union[:, 1].max() > paper_height
    ):
        raise RuntimeError("Q2_TARGET_RECTANGLE_DOES_NOT_FIT")
    return targets


def _build_move(
    *,
    cycle_index: int,
    piece_id: int,
    source_vertices_mm: np.ndarray,
    target_vertices_mm: np.ndarray,
    mapper: ArmCoordinateMapper,
    config: Q2RuntimeConfig,
) -> SingleMovePlan:
    transform = compute_rigid_transform(source_vertices_mm, target_vertices_mm)
    if not transform.valid or transform.max_error_mm > float(config.vertex_max_error_mm):
        raise RuntimeError(
            "Q2_PLAN_GEOMETRY_RESIDUAL: "
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

    if config.pick_height is None or config.release_height is None:
        raise RuntimeError("CALIBRATION_REQUIRED: missing pick/release height")
    source_robot = mapper.paper_to_robot(
        source.x_mm,
        source.y_mm,
        float(config.pick_height),
        roll_deg=0.0,
    )
    source_robot.x += float(config.pick_robot_xy_offset_mm[0])
    source_robot.y += float(config.pick_robot_xy_offset_mm[1])
    target_robot = mapper.paper_to_robot(
        target.x_mm,
        target.y_mm,
        float(config.release_height),
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
            "Q2_PLAN_ROLL_OUT_OF_RANGE: no equivalent wrist rotation stays "
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
        template_id=f"Q2_{piece_id + 1}",
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
        confidence=1.0,
        reason_selected="Q2_EXACT_GEOMETRIC_SOLUTION",
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


def plan_white_puzzle_moves(
    puzzle: ImagePuzzleInput,
    solution: Solution,
    mapper: ArmCoordinateMapper,
    config: Q2RuntimeConfig,
) -> list[PieceMove]:
    if not is_executable_solution(solution):
        raise RuntimeError("Q2_SOLUTION_NOT_EXECUTABLE")

    source_by_id = {piece.id: piece for piece in puzzle.pieces}
    targets = target_solution_vertices(puzzle, solution)
    placed_items: list[PlacedPiece] = sorted(
        solution.placed_pieces,
        key=lambda item: source_by_id[item.piece_id].area,
        reverse=True,
    )
    moves: list[PieceMove] = []
    for placed in placed_items:
        source_piece = source_by_id[placed.piece_id]
        source_vertices = np.asarray(
            [point.as_tuple() for point in source_piece.vertices],
            dtype=np.float64,
        )
        moves.append(
            _build_move(
                cycle_index=len(moves),
                piece_id=placed.piece_id,
                source_vertices_mm=source_vertices,
                target_vertices_mm=targets[placed.piece_id],
                mapper=mapper,
                config=config,
            )
        )
    return moves
