from puzzle_solver import PuzzleSolver, RigidTransform
from puzzle_solver.models import Piece, PlacedPiece
from puzzle_solver.sample_data import overlapping_candidate_puzzle
from puzzle_solver.validation import check_overlap


def test_common_edge_is_not_area_overlap() -> None:
    left = PlacedPiece.from_piece(
        Piece(0, [(0, 0), (50, 0), (50, 60), (0, 60)]), RigidTransform()
    )
    right = PlacedPiece.from_piece(
        Piece(1, [(50, 0), (100, 0), (100, 60), (50, 60)]), RigidTransform()
    )

    valid, area = check_overlap([left], right, tolerance_mm2=0.5)
    assert valid
    assert area == 0.0


def test_positive_area_overlap_is_rejected() -> None:
    first = PlacedPiece.from_piece(
        Piece(0, [(0, 0), (50, 0), (50, 50), (0, 50)]), RigidTransform()
    )
    overlapping = PlacedPiece.from_piece(
        Piece(1, [(25, 0), (75, 0), (75, 50), (25, 50)]), RigidTransform()
    )

    valid, area = check_overlap([first], overlapping, tolerance_mm2=0.5)
    assert not valid
    assert area == 1250.0


def test_dfs_prunes_an_overlapping_edge_match() -> None:
    solver = PuzzleSolver()
    solution = solver.solve(overlapping_candidate_puzzle())

    assert not solution.success
    assert solution.reason == "No valid assembly found"
    assert solver.stats.overlap_rejections > 0

