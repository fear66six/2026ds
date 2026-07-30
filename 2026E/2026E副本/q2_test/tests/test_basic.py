import math

import pytest

from puzzle_solver import Piece, Point, PuzzleSolver
from puzzle_solver.sample_data import (
    board_scattered_four_piece_rectangle,
    irregular_three_piece_rectangle,
    scattered_rotated_four_piece_rectangle,
    simple_four_piece_rectangle,
)


def test_piece_derives_geometry_for_triangle_and_pentagon() -> None:
    triangle = Piece(7, [(0, 0), (30, 0), (0, 40)])
    pentagon = Piece(8, [(0, 0), (30, 0), (40, 20), (20, 35), (0, 20)])

    assert triangle.area == pytest.approx(600.0)
    assert [edge.length for edge in triangle.edges] == pytest.approx([30, 50, 40])
    assert triangle.centroid == Point(10.0, 40.0 / 3.0)
    assert len(pentagon.edges) == 5
    assert pentagon.bounds == pytest.approx((0, 0, 40, 35))
    assert math.degrees(triangle.edges[0].angle) == pytest.approx(0.0)


def test_four_piece_rectangle_solves() -> None:
    solver = PuzzleSolver()
    solution = solver.solve(simple_four_piece_rectangle())

    assert solution.success, solution.reason
    assert solution.rectangle_width_mm == pytest.approx(100.0)
    assert solution.rectangle_height_mm == pytest.approx(70.0)
    assert {pose["piece_id"] for pose in solution.poses} == {0, 1, 2, 3}
    assert len(solution.connections) == 3


def test_triangle_and_quadrilaterals_form_irregular_three_piece_rectangle() -> None:
    solution = PuzzleSolver().solve(irregular_three_piece_rectangle())

    assert solution.success, solution.reason
    assert solution.rectangle_width_mm == pytest.approx(110.0)
    assert solution.rectangle_height_mm == pytest.approx(60.0)


def test_arbitrarily_rotated_and_translated_inputs_are_solved_without_scaling() -> None:
    pieces = scattered_rotated_four_piece_rectangle()
    source_areas = {piece.id: piece.area for piece in pieces}
    solution = PuzzleSolver().solve(pieces)

    assert solution.success, solution.reason
    assert solution.rectangle_width_mm == pytest.approx(100.0, abs=1e-6)
    assert solution.rectangle_height_mm == pytest.approx(70.0, abs=1e-6)
    for placed in solution.placed_pieces:
        assert placed.polygon.area == pytest.approx(source_areas[placed.piece_id], abs=1e-6)


def test_board_scattered_irregular_pieces_form_rectangle() -> None:
    pieces = board_scattered_four_piece_rectangle()
    solution = PuzzleSolver().solve(pieces)

    assert solution.success, solution.reason
    assert solution.rectangle_width_mm == pytest.approx(100.0, abs=2e-6)
    assert solution.rectangle_height_mm == pytest.approx(70.0, abs=2e-6)
    assert max(piece.bounds[3] for piece in pieces) < 148.5
