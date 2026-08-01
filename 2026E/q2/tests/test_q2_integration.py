import pytest
from pathlib import Path
import sys

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_PACKAGE_ROOT = PROJECT_ROOT / "2026E"
if str(PROJECT_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PACKAGE_ROOT))

from q1.calibration import ArmCoordinateMapper
from q1.main import _apply_robot_fields
from q1.models import Snapshot
from q2.analyzer import WhitePuzzleAnalyzer, is_executable_solution
from q2.motion import plan_white_puzzle_moves
from q2.puzzle_solver.models import Solution
from q2.runtime_config import Q2RuntimeConfig


ROBOT_CONFIG = PROJECT_ROOT / "2026E" / "q1" / "config" / "robot_config.json"
UPSTREAM_BOARD = PROJECT_ROOT / "q2" / "board_solution.png"


def test_q2_camera_orientation_solve_and_q1_motion_contract() -> None:
    if not UPSTREAM_BOARD.is_file():
        pytest.skip(f"missing fixture image: {UPSTREAM_BOARD}")
    portrait = cv2.imread(str(UPSTREAM_BOARD), cv2.IMREAD_COLOR)
    assert portrait is not None
    snapshot = Snapshot(
        frame=cv2.transpose(portrait),
        timestamp=0.0,
        sharpness=0.0,
        brightness=0.0,
        motion_score=0.0,
        path=str(UPSTREAM_BOARD),
    )
    analyzer = WhitePuzzleAnalyzer()
    scene = analyzer.analyze(snapshot, 0)

    assert scene.paper_valid
    assert len(scene.pieces) == 4
    assert scene.scene_valid
    assert scene.exact_solution
    assert not scene.best_effort
    assert scene.official_dimensions_valid is True
    assert analyzer.last_puzzle is not None
    assert analyzer.last_solution is not None

    robot_data = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    config = Q2RuntimeConfig(robot_config=ROBOT_CONFIG)
    _apply_robot_fields(config, robot_data)
    moves = plan_white_puzzle_moves(
        analyzer.last_puzzle,
        analyzer.last_solution,
        ArmCoordinateMapper(ROBOT_CONFIG),
        config,
    )

    assert len(moves) == 4
    assert all(move.target_pose_paper.y_mm > scene.divider_y_mm for move in moves)
    assert all(
        move.source_pose_robot is not None
        and move.approach_pose is not None
        and move.rotate_pose is not None
        and move.transfer_pose is not None
        and move.release_pose is not None
        for move in moves
    )


def test_best_effort_and_invalid_dimensions_are_not_executable() -> None:
    assert not is_executable_solution(
        Solution(
            success=True,
            best_effort=True,
            official_dimensions_valid=True,
        )
    )
    assert not is_executable_solution(
        Solution(
            success=True,
            best_effort=False,
            official_dimensions_valid=False,
        )
    )
