"""Adapter from a local board image to geometric solver input."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from .config import SolverConfig
from .models import Piece
from .raster_detection import (
    DEFAULT_HSV_RANGES,
    MAX_PIECES,
    MAX_SIMPLIFICATION_AREA_LOSS_RATIO,
    PaperFrame,
    PROTECTED_SHORT_EDGE_CM,
    detect_board_divider,
    detect_divider_line,
    detect_paper,
    detect_pieces,
    detect_polygon_vertices,
)


# Raster contours can contain a short edge introduced by aliasing even when
# the source fragment is valid.  Keep this aligned with image_solver_config so
# detection and DFS apply the same lower bound.
RASTER_MIN_EDGE_LENGTH_MM = 8.0
RASTER_PROTECTED_MIN_EDGE_LENGTH_MM = PROTECTED_SHORT_EDGE_CM * 10.0
MAX_COMBINATION_CANDIDATES = 12


@dataclass(frozen=True)
class ImagePuzzleInput:
    """Detected piece geometry and physical board layout in millimetres."""

    pieces: tuple[Piece, ...]
    paper_size_mm: tuple[float, float]
    layout: Literal["top-bottom", "left-right"]
    divider_y_mm: float | None
    divider_x_mm: float | None
    image_path: Path
    detected_candidate_count: int = 0


@dataclass(frozen=True)
class _RasterPieceCandidate:
    """One usable polygon plus evidence from its unsimplified contour."""

    source_index: int
    piece: Piece
    contour_area_mm2: float

    @property
    def area_error_ratio(self) -> float:
        return abs(self.contour_area_mm2 - self.piece.area) / max(
            self.contour_area_mm2,
            1e-9,
        )


def _edge_compatibility_penalty(candidates: tuple[_RasterPieceCandidate, ...]) -> float:
    """Measure whether every fragment has at least one plausible neighbour."""

    lengths = [edge.length for candidate in candidates for edge in candidate.piece.edges]
    tolerance = min(10.0, max(3.0, 0.18 * float(np.median(lengths))))
    penalty = 0.0
    for candidate in candidates:
        other_edges = [
            edge
            for other in candidates
            if other.source_index != candidate.source_index
            for edge in other.piece.edges
        ]
        best_error = min(
            abs(edge.length - other.length)
            for edge in candidate.piece.edges
            for other in other_edges
        )
        penalty += max(0.0, best_error - tolerance)
    return penalty


def _piece_combination_score(
    candidates: tuple[_RasterPieceCandidate, ...],
) -> tuple[float, float, float, float, tuple[int, ...]]:
    """Rank four-contour hypotheses without assuming the smallest is noise."""

    area_errors = [candidate.area_error_ratio for candidate in candidates]
    grossly_distorted = float(sum(error > 0.25 for error in area_errors))
    total_area = sum(candidate.piece.area for candidate in candidates)
    # The smallest official rectangle may contain the configured 600 mm2
    # raster gap, while overlap pruning protects the upper area limit.
    minimum_piece_area = 90.0 * 50.0 - 600.0
    maximum_piece_area = 120.0 * 90.0
    target_area_error = max(
        0.0,
        minimum_piece_area - total_area,
        total_area - maximum_piece_area,
    )
    return (
        grossly_distorted,
        sum(area_errors),
        target_area_error,
        _edge_compatibility_penalty(candidates),
        tuple(candidate.source_index for candidate in candidates),
    )


def _select_best_piece_candidates(
    candidates: list[_RasterPieceCandidate],
) -> list[_RasterPieceCandidate]:
    """Select the strongest four-piece hypothesis from excess contours."""

    if len(candidates) <= MAX_PIECES:
        return candidates
    pool = sorted(
        candidates,
        key=lambda candidate: (
            candidate.area_error_ratio > 0.25,
            candidate.area_error_ratio,
            candidate.source_index,
        ),
    )[:MAX_COMBINATION_CANDIDATES]
    best = min(
        combinations(pool, MAX_PIECES),
        key=_piece_combination_score,
    )
    return sorted(best, key=lambda candidate: candidate.source_index)


def _to_solver_piece(
    piece_id: int,
    vertices_cm: np.ndarray,
    contour_area_cm2: float | None = None,
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
    minimum_edge = min(edge.length for edge in piece.edges)
    if minimum_edge < RASTER_MIN_EDGE_LENGTH_MM:
        if (
            contour_area_cm2 is None
            or minimum_edge < RASTER_PROTECTED_MIN_EDGE_LENGTH_MM
            or contour_area_cm2 <= 1e-9
        ):
            return None
        contour_area_mm2 = contour_area_cm2 * 100.0
        area_loss_ratio = abs(contour_area_mm2 - piece.area) / contour_area_mm2
        if area_loss_ratio > MAX_SIMPLIFICATION_AREA_LOSS_RATIO:
            return None
    return piece


def load_q2_image_pieces(image_path: str | Path) -> ImagePuzzleInput:
    """Detect source-region polygons and convert centimetres to millimetres."""

    path = Path(image_path).expanduser().resolve()
    frame = cv2.imread(str(path))
    if frame is None:
        raise ValueError(f"cannot read image: {path}")

    paper = detect_paper(frame)
    if paper is None:
        raise ValueError("Q2 detector did not find the A4 board")
    divider = detect_board_divider(frame, paper)

    # Normalize a left-right board to the established top-bottom detection
    # path. Pixel morphology and polygon simplification can otherwise move
    # raster vertices by roughly one millimetre after a 90-degree image
    # rotation. Mapping the detected coordinates back is a rigid transform,
    # so the physical piece geometry is neither scaled nor reflected.
    detection_frame = frame
    detection_paper = paper
    detection_layout: Literal["top-bottom", "left-right"] = divider.layout
    if divider.layout == "left-right":
        detection_frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
        normalized_paper = detect_paper(detection_frame)
        if normalized_paper is None:
            raise ValueError("Q2 detector did not find the rotated A4 board")
        detection_paper = normalized_paper
        detection_layout = "top-bottom"

    detected = detect_pieces(
        detection_frame,
        detection_paper,
        divider.position_cm,
        DEFAULT_HSV_RANGES,
        detection_layout,
    )
    detected = [
        piece
        for piece in detected
        if piece.in_source_region
        and piece.center_cm[1] < divider.position_cm - 0.5
    ]
    candidates: list[_RasterPieceCandidate] = []
    for piece_id, detected_piece in enumerate(detected):
        vertices_cm = detect_polygon_vertices(detected_piece, detection_paper)
        if divider.layout == "left-right":
            normalized_vertices = np.asarray(vertices_cm, dtype=np.float64)
            vertices_cm = np.column_stack(
                (
                    normalized_vertices[:, 1],
                    paper.height_cm - normalized_vertices[:, 0],
                )
            )
        solver_piece = _to_solver_piece(
            piece_id,
            vertices_cm,
            detected_piece.area_cm2,
        )
        if solver_piece is not None:
            candidates.append(
                _RasterPieceCandidate(
                    source_index=piece_id,
                    piece=solver_piece,
                    contour_area_mm2=detected_piece.area_cm2 * 100.0,
                )
            )

    if not candidates:
        raise ValueError("Q2 detector did not find valid upper-board pieces")
    selected = _select_best_piece_candidates(candidates)
    pieces = tuple(
        Piece(piece_id, candidate.piece.vertices)
        for piece_id, candidate in enumerate(selected)
    )
    return ImagePuzzleInput(
        pieces=pieces,
        paper_size_mm=(
            paper.width_cm * 10.0,
            paper.height_cm * 10.0,
        ),
        layout=divider.layout,
        divider_y_mm=(
            divider.position_cm * 10.0
            if divider.layout == "top-bottom"
            else None
        ),
        divider_x_mm=(
            divider.position_cm * 10.0
            if divider.layout == "left-right"
            else None
        ),
        image_path=path,
        detected_candidate_count=len(candidates),
    )


def q2_puzzle_from_rectified(
    rectified_bgr: np.ndarray,
    *,
    paper_size_mm: tuple[float, float] = (210.0, 297.0),
    pixels_per_mm: float = 5.0,
    divider_y_mm: float | None = None,
    image_path: str | Path | None = None,
) -> ImagePuzzleInput:
    """Detect Q2 pieces in an A4 image already rectified by Q1."""

    if rectified_bgr is None or rectified_bgr.ndim != 3:
        raise ValueError("a rectified BGR colour image is required")
    if pixels_per_mm <= 0:
        raise ValueError("pixels_per_mm must be positive")

    paper_width_mm, paper_height_mm = (float(value) for value in paper_size_mm)
    if paper_width_mm <= 0 or paper_height_mm <= 0:
        raise ValueError("paper dimensions must be positive")

    image_height, image_width = rectified_bgr.shape[:2]
    scale_x = image_width / paper_width_mm
    scale_y = image_height / paper_height_mm
    if abs(scale_x - scale_y) > max(scale_x, scale_y) * 0.03:
        raise ValueError("rectified image scale is inconsistent across axes")
    if abs(0.5 * (scale_x + scale_y) - pixels_per_mm) > pixels_per_mm * 0.03:
        raise ValueError("rectified image does not match pixels_per_mm")

    paper = PaperFrame(
        corners_px=np.asarray(
            (
                (0.0, 0.0),
                (image_width - 1.0, 0.0),
                (image_width - 1.0, image_height - 1.0),
                (0.0, image_height - 1.0),
            ),
            dtype=np.float32,
        ),
        px_per_cm=0.5 * (scale_x + scale_y) * 10.0,
        width_cm=paper_width_mm / 10.0,
        height_cm=paper_height_mm / 10.0,
    )
    divider_cm = (
        detect_divider_line(rectified_bgr, paper)
        if divider_y_mm is None
        else float(divider_y_mm) / 10.0
    )
    detected = detect_pieces(
        rectified_bgr,
        paper,
        divider_cm,
        DEFAULT_HSV_RANGES,
        "top-bottom",
    )
    detected = [
        piece
        for piece in detected
        if piece.in_source_region and piece.center_cm[1] < divider_cm - 0.5
    ]

    candidates: list[_RasterPieceCandidate] = []
    for piece_id, detected_piece in enumerate(detected):
        solver_piece = _to_solver_piece(
            piece_id,
            detect_polygon_vertices(detected_piece, paper),
            detected_piece.area_cm2,
        )
        if solver_piece is not None:
            candidates.append(
                _RasterPieceCandidate(
                    source_index=piece_id,
                    piece=solver_piece,
                    contour_area_mm2=detected_piece.area_cm2 * 100.0,
                )
            )

    if not candidates:
        raise ValueError("Q2 detector did not find valid source-region pieces")
    selected = _select_best_piece_candidates(candidates)
    pieces = tuple(
        Piece(piece_id, candidate.piece.vertices)
        for piece_id, candidate in enumerate(selected)
    )
    return ImagePuzzleInput(
        pieces=pieces,
        paper_size_mm=(paper_width_mm, paper_height_mm),
        layout="top-bottom",
        divider_y_mm=divider_cm * 10.0,
        divider_x_mm=None,
        image_path=Path(image_path) if image_path is not None else Path("capture.png"),
        detected_candidate_count=len(candidates),
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
    minimum_detected_edge = min(edge_lengths)
    solver_minimum_edge = (
        RASTER_PROTECTED_MIN_EDGE_LENGTH_MM
        if minimum_detected_edge < RASTER_MIN_EDGE_LENGTH_MM
        else RASTER_MIN_EDGE_LENGTH_MM
    )
    return SolverConfig(
        min_edge_length_mm=solver_minimum_edge,
        length_tolerance_mm=length_tolerance,
        angle_tolerance_deg=12.0,
        outer_edge_tolerance_mm=4.0,
        overlap_tolerance_mm2=20.0,
        area_tolerance_mm2=max(150.0, total_area * 0.22),
        max_final_gap_ratio=0.07,
        max_final_gap_area_mm2=600.0,
        bbox_tolerance_mm=20.0,
        rectangle_dimension_tolerance_mm=12.0,
        official_dimension_tolerance_mm=3.0,
        max_rectangle_boundary_gap_mm=5.0,
        allow_fitted_rectangle=True,
        partial_min_residual_mm=15.0,
        approximate_full_match_tolerance_mm=max(12.0, length_tolerance),
        min_connection_length_mm=8.0,
        open_edge_merge_angle_tolerance_deg=5.0,
        # Composite boundary segments must share a real assembly vertex.
        # A wide tolerance bridges unrelated raster edges and destroys the
        # original open-edge alternatives before DFS can try them.
        open_edge_merge_distance_tolerance_mm=1.0,
        find_best_solution=True,
        best_solution_stop_area_ratio=stop_area_ratio,
        max_search_nodes=None,
        max_candidate_attempts=None,
        max_search_seconds=60.0,
        return_best_effort_on_failure=True,
    )
