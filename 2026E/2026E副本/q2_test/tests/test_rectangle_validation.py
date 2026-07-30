import math

import pytest
from shapely.geometry import Polygon

from puzzle_solver import Piece, PuzzleSolver, RigidTransform, SolverConfig
from puzzle_solver.models import PlacedPiece
from puzzle_solver.sample_data import out_of_range_rectangle, simple_four_piece_rectangle
from puzzle_solver.validation import check_bbox, check_outer_edges


def test_final_rectangle_rejects_out_of_range_dimensions() -> None:
    solution = PuzzleSolver().solve(out_of_range_rectangle())

    assert not solution.success
    assert solution.reason == "No valid assembly found"


def test_every_solved_piece_has_a_complete_outer_edge() -> None:
    solution = PuzzleSolver().solve(simple_four_piece_rectangle())
    assert solution.success
    assert solution.rectangle is not None

    assert check_outer_edges(
        solution.placed_pieces,
        solution.rectangle,
        SolverConfig().outer_edge_tolerance_mm,
    )


def test_piece_wholly_inside_rectangle_has_no_outer_edge() -> None:
    inner = PlacedPiece.from_piece(
        Piece(9, [(30, 20), (70, 20), (70, 50), (30, 50)]), RigidTransform()
    )
    rectangle = Polygon([(0, 0), (100, 0), (100, 70), (0, 70)])

    assert not check_outer_edges([inner], rectangle, tolerance_mm=2.0)


def test_oriented_bbox_pruning_accepts_rotation_and_rejects_oversize() -> None:
    angle = math.radians(37.0)
    allowed_piece = Piece(0, [(0, 0), (100, 0), (100, 70), (0, 70)])
    oversized_piece = Piece(1, [(0, 0), (130, 0), (130, 70), (0, 70)])
    allowed = PlacedPiece.from_piece(allowed_piece, RigidTransform(angle))
    oversized = PlacedPiece.from_piece(oversized_piece, RigidTransform(angle))

    assert check_bbox([], allowed, SolverConfig())
    assert not check_bbox([], oversized, SolverConfig())


def test_input_limits_are_reported_without_search() -> None:
    too_many = [Piece(index, [(0, 0), (20, 0), (0, 20)]) for index in range(5)]
    solution = PuzzleSolver().solve(too_many)

    assert not solution.success
    assert solution.reason == "At most 4 pieces are supported"


def test_input_edge_shorter_than_twenty_mm_is_rejected() -> None:
    piece = Piece(0, [(0, 0), (19, 0), (0, 30)])
    solution = PuzzleSolver().solve([piece])

    assert not solution.success
    assert solution.reason == "Piece 0 has an edge shorter than 20 mm"
