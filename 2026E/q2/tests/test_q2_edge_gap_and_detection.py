from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_PACKAGE_ROOT = PROJECT_ROOT / "2026E"
if str(PROJECT_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_PACKAGE_ROOT))

from q1.geometry import apply_uniform_shared_edge_gap
from q2.puzzle_solver.image_input import (
    _area_outlier_warning,
    _RasterPieceCandidate,
    q2_puzzle_from_rectified,
)
from q2.puzzle_solver.models import Piece


def test_apply_uniform_shared_edge_gap_detects_all_rectangle_adjacencies() -> None:
    """Four rectangles in a 2x2 grid have four internal seams, not only three DFS edges."""

    targets = {
        0: np.array([[0.0, 0.0], [50.0, 0.0], [50.0, 40.0], [0.0, 40.0]], dtype=np.float64),
        1: np.array([[50.0, 0.0], [100.0, 0.0], [100.0, 40.0], [50.0, 40.0]], dtype=np.float64),
        2: np.array([[0.0, 40.0], [50.0, 40.0], [50.0, 80.0], [0.0, 80.0]], dtype=np.float64),
        3: np.array([[50.0, 40.0], [100.0, 40.0], [100.0, 80.0], [50.0, 80.0]], dtype=np.float64),
    }
    only_tree_edge = ((0, 1, 0, 1),)
    tree_result = apply_uniform_shared_edge_gap(
        targets,
        5.0,
        shared_edge_pairs=only_tree_edge,
    )
    auto_result = apply_uniform_shared_edge_gap(targets, 5.0)

    def horizontal_gap(piece_a: np.ndarray, piece_b: np.ndarray) -> float:
        return float(piece_b[:, 0].min() - piece_a[:, 0].max())

    tree_gap_01 = horizontal_gap(tree_result[0], tree_result[1])
    auto_gap_01 = horizontal_gap(auto_result[0], auto_result[1])
    auto_gap_02 = float(auto_result[2][:, 1].min() - auto_result[0][:, 1].max())
    auto_gap_23 = horizontal_gap(auto_result[2], auto_result[3])

    assert auto_gap_01 == pytest.approx(5.0, abs=0.2)
    assert auto_gap_02 == pytest.approx(5.0, abs=0.2)
    assert auto_gap_23 == pytest.approx(5.0, abs=0.2)
    assert tree_gap_01 > 5.0


def test_area_outlier_warning_does_not_block() -> None:
    large = Piece(0, [(0.0, 0.0), (100.0, 0.0), (100.0, 200.0), (0.0, 200.0)])
    tiny = Piece(1, [(0.0, 0.0), (30.0, 0.0), (0.0, 40.0)])
    candidates = [
        _RasterPieceCandidate(0, large, large.area),
        _RasterPieceCandidate(1, tiny, tiny.area),
        _RasterPieceCandidate(2, large, large.area),
        _RasterPieceCandidate(3, large, large.area),
    ]
    warning = _area_outlier_warning(candidates)
    assert warning is not None
    assert "much smaller than the others" in warning


def test_q2_puzzle_from_rectified_recovers_four_similar_fragments() -> None:
    canvas = np.zeros((1485, 1050, 3), dtype=np.uint8)
    divider_y = 750
    cv2.line(canvas, (0, divider_y), (1050, divider_y), (255, 255, 255), 4)
    shapes = [
        np.array([[120, 180], [320, 160], [340, 320], [100, 340]], np.int32),
        np.array([[420, 140], [620, 130], [640, 300], [400, 310]], np.int32),
        np.array([[700, 170], [920, 190], [900, 340], [680, 320]], np.int32),
        np.array([[250, 420], [500, 400], [520, 580], [230, 600]], np.int32),
    ]
    for shape in shapes:
        cv2.fillPoly(canvas, [shape], (240, 240, 240))

    puzzle = q2_puzzle_from_rectified(canvas, divider_y_mm=148.5)
    areas = [piece.area for piece in puzzle.pieces]
    assert len(puzzle.pieces) == 4
    assert min(areas) > 0.55 * float(np.median(areas))
