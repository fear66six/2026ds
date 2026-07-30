import math

import pytest

from puzzle_solver import Piece, PuzzleSolver, calculate_pose
from puzzle_solver.models import OpenEdge
from puzzle_solver.sample_data import reversed_endpoint_rectangle


def test_pose_generator_tries_both_endpoint_correspondences() -> None:
    candidate = Piece(1, [(0, 0), (30, 0), (15, 20)])
    edge = candidate.edges[0]
    open_edge = OpenEdge(0, 0, edge.p1, edge.p2)

    direct = calculate_pose(open_edge, edge, "direct")
    reversed_pose = calculate_pose(open_edge, edge, "reversed")

    assert direct.apply(edge.p1) == open_edge.p1
    assert direct.apply(edge.p2).x == pytest.approx(open_edge.p2.x)
    assert reversed_pose.apply(edge.p1).x == pytest.approx(open_edge.p2.x)
    assert reversed_pose.apply(edge.p2).x == pytest.approx(open_edge.p1.x)
    assert abs(math.degrees(reversed_pose.rotation_rad)) == pytest.approx(180.0)


def test_direct_mapping_fails_before_reversed_mapping_succeeds() -> None:
    solver = PuzzleSolver()
    solution = solver.solve(reversed_endpoint_rectangle())

    assert solution.success, solution.reason
    assert solver.stats.direct_mapping_attempts >= 1
    assert solver.stats.side_rejections >= 1
    assert solver.stats.reversed_mapping_attempts >= 1
    assert solution.rectangle_width_mm == pytest.approx(120.0)
    assert solution.rectangle_height_mm == pytest.approx(50.0)

