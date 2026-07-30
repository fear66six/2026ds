import pytest

from puzzle_solver import PuzzleSolver
from puzzle_solver.sample_data import (
    backtracking_rectangle,
    partial_edge_three_piece_rectangle,
)


def test_solver_backtracks_after_a_plausible_dead_branch() -> None:
    solver = PuzzleSolver()
    solution = solver.solve(backtracking_rectangle())

    assert solution.success, solution.reason
    assert solver.stats.backtracks > 0
    assert solver.stats.candidate_attempts > len(solution.placed_pieces) - 1
    assert solution.rectangle_width_mm == pytest.approx(100.0)
    assert solution.rectangle_height_mm == pytest.approx(70.0)


def test_state_cache_is_used_and_reset_between_solves() -> None:
    solver = PuzzleSolver()
    first = solver.solve(backtracking_rectangle())
    first_signatures = len(solver.visited_states)
    second = solver.solve(backtracking_rectangle())

    assert first.success and second.success
    assert first_signatures > 0
    assert len(solver.visited_states) == first_signatures


def test_open_edge_residual_supports_t_junction_partition() -> None:
    solver = PuzzleSolver()
    solution = solver.solve(partial_edge_three_piece_rectangle())

    assert solution.success, solution.reason
    assert solution.rectangle_width_mm == pytest.approx(120.0)
    assert solution.rectangle_height_mm == pytest.approx(70.0)
    assert any(connection.p1.x == pytest.approx(50.0) for connection in solution.connections)
