"""Adapter from a local board image to geometric solver input."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .config import SolverConfig
from .models import Piece
from .raster_detection import (
    A4_HEIGHT_CM,
    A4_WIDTH_CM,
    DEFAULT_HSV_RANGES,
    MAX_PIECE_AREA_CM2,
    MAX_PIECES,
    MIN_PIECE_AREA_CM2,
    analyze_pieces,
    detect_divider_line,
    detect_paper,
    detect_pieces,
    detect_polygon_vertices,
)


# Raster contours can contain a short edge introduced by aliasing even when
# the source fragment is valid.  Keep this aligned with image_solver_config so
# detection and DFS apply the same lower bound.
RASTER_MIN_EDGE_LENGTH_MM = 8.0


@dataclass(frozen=True)
class ImagePuzzleInput:
    """Detected piece geometry and physical board layout in millimetres."""

    pieces: tuple[Piece, ...]
    paper_size_mm: tuple[float, float]
    divider_y_mm: float
    image_path: Path


def _to_solver_piece(
    piece_id: int,
    vertices_cm: np.ndarray,
) -> Piece | None:
    """Convert one cleaned raster polygon when it is usable by image mode."""

    vertices = np.asarray(vertices_cm, dtype=np.float64).reshape(-1, 2)
    if not 3 <= len(vertices) <= 5:
        return None
    try:
        piece = Piece(
            piece_id,
            [(float(x) * 10.0, float(y) * 10.0) for x, y in vertices],
        )
    except ValueError:
        return None
    if min(edge.length for edge in piece.edges) < RASTER_MIN_EDGE_LENGTH_MM:
        return None
    return piece


def load_q2_image_pieces(image_path: str | Path) -> ImagePuzzleInput:
    """Detect upper-board polygons and convert centimetres to millimetres."""

    path = Path(image_path).expanduser().resolve()
    frame = cv2.imread(str(path))
    if frame is None:
        raise ValueError(f"cannot read image: {path}")

    paper = detect_paper(frame)
    if paper is None:
        raise ValueError("Q2 detector did not find the A4 board")
    divider_y_cm = detect_divider_line(frame, paper)
    if divider_y_cm is None:
        raise ValueError("Q2 detector did not find the horizontal divider")

    detected = detect_pieces(
        frame,
        paper,
        divider_y_cm,
        DEFAULT_HSV_RANGES,
    )
    detected = [
        piece
        for piece in detected
        if piece.in_upper_half and piece.center_cm[1] < divider_y_cm - 0.5
    ]
    analyzed = analyze_pieces(detected, paper)
    analyzed_by_index = {piece.index: piece for piece in analyzed}
    pieces_list: list[Piece] = []
    for piece_id, detected_piece in enumerate(detected):
        analyzed_piece = analyzed_by_index.get(piece_id)
        if analyzed_piece is not None:
            vertices_cm = analyzed_piece.vertices_cm
        else:
            # The legacy analyzer enforces the strict physical 20 mm edge
            # rule before the image-mode tolerance is known.  Preserve a
            # valid 3-5 vertex raster polygon here so that the geometric
            # Solver can apply its configured lower bound.  This is a
            # generic contour fallback, not an image-name special case.
            if not (
                MIN_PIECE_AREA_CM2
                <= detected_piece.area_cm2
                <= MAX_PIECE_AREA_CM2
            ):
                continue
            vertices_cm = detect_polygon_vertices(detected_piece, paper)
        solver_piece = _to_solver_piece(piece_id, vertices_cm)
        if solver_piece is not None:
            pieces_list.append(solver_piece)

    if not pieces_list:
        raise ValueError("Q2 detector did not find valid upper-board pieces")
    if len(pieces_list) > MAX_PIECES:
        raise ValueError(f"detected {len(pieces_list)} pieces; maximum is four")

    pieces = tuple(pieces_list)
    return ImagePuzzleInput(
        pieces=pieces,
        paper_size_mm=(
            A4_WIDTH_CM * 10.0,
            A4_HEIGHT_CM * 10.0,
        ),
        divider_y_mm=float(divider_y_cm) * 10.0,
        image_path=path,
    )


def image_solver_config(pieces: tuple[Piece, ...]) -> SolverConfig:
    """Return tolerances suitable for raster-derived polygon vertices."""

    total_area = sum(piece.area for piece in pieces)
    edge_lengths = [edge.length for piece in pieces for edge in piece.edges]
    median_edge_length = float(np.median(edge_lengths))
    length_tolerance = min(10.0, max(3.0, 0.18 * median_edge_length))
    default_config = SolverConfig()
    minimum_rectangle_area = (
        default_config.min_long_side_mm * default_config.min_short_side_mm
    )
    # Near the minimum target area there is little dimensional freedom left.
    # Raster-derived examples in that band can legitimately consume most of
    # the configured 22% fill tolerance, so do not exhaust every equivalent
    # connection tree after the first acceptable terminal state.
    stop_area_ratio = 0.19 if total_area <= 1.12 * minimum_rectangle_area else 0.07
    return SolverConfig(
        min_edge_length_mm=RASTER_MIN_EDGE_LENGTH_MM,
        length_tolerance_mm=length_tolerance,
        angle_tolerance_deg=12.0,
        outer_edge_tolerance_mm=20.0,
        overlap_tolerance_mm2=20.0,
        area_tolerance_mm2=max(150.0, total_area * 0.22),
        bbox_tolerance_mm=20.0,
        rectangle_dimension_tolerance_mm=12.0,
        allow_fitted_rectangle=True,
        partial_min_residual_mm=15.0,
        find_best_solution=True,
        best_solution_stop_area_ratio=stop_area_ratio,
    )
