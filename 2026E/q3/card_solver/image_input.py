"""Public adapter from a colour photograph to standalone Q3 observations."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from .config import PatternConfig, SolverConfig
from .edge_features import make_observation
from .models import CardPuzzleInput, Piece
from .piece_detection import (
    DetectedFragment,
    RectifiedBoard,
    detect_and_rectify_board,
    detect_divider,
    detect_fragments,
)


@dataclass(frozen=True)
class _VisualPieceCandidate:
    """One fitted fragment plus evidence from its unsimplified contour."""

    source_index: int
    piece: Piece
    fragment: DetectedFragment

    @property
    def area_error_ratio(self) -> float:
        return abs(self.fragment.area_mm2 - self.piece.area) / max(
            self.fragment.area_mm2,
            1e-9,
        )


def _edge_compatibility_penalty(
    candidates: tuple[_VisualPieceCandidate, ...],
    config: SolverConfig,
) -> float:
    """Penalize a contour that has no plausible internal edge partner."""

    lengths = [
        edge.length
        for candidate in candidates
        for edge in candidate.piece.edges
    ]
    tolerance = min(
        config.approximate_full_match_tolerance_mm,
        max(config.length_tolerance_mm, 0.18 * float(np.median(lengths))),
    )
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
    candidates: tuple[_VisualPieceCandidate, ...],
    config: SolverConfig,
) -> tuple[float, float, float, float, tuple[int, ...]]:
    """Rank four-contour hypotheses without assuming small means noise."""

    area_errors = [candidate.area_error_ratio for candidate in candidates]
    grossly_distorted = float(
        sum(error > config.artwork_hull_max_added_area_ratio for error in area_errors)
    )
    total_area = sum(candidate.piece.area for candidate in candidates)
    minimum_target_area = max(
        0.0,
        (config.min_short_side_mm - config.rectangle_dimension_tolerance_mm)
        * config.image_min_long_side_mm
        - config.max_final_gap_area_mm2,
    )
    maximum_target_area = (
        config.max_short_side_mm + config.rectangle_dimension_tolerance_mm
    ) * (config.max_long_side_mm + config.rectangle_dimension_tolerance_mm)
    target_area_error = max(
        0.0,
        minimum_target_area - total_area,
        total_area - maximum_target_area,
    )
    return (
        grossly_distorted,
        target_area_error,
        _edge_compatibility_penalty(candidates, config),
        sum(area_errors),
        tuple(candidate.source_index for candidate in candidates),
    )


def _select_best_piece_candidates(
    candidates: list[_VisualPieceCandidate],
    config: SolverConfig,
) -> list[_VisualPieceCandidate]:
    """Select the strongest four-piece hypothesis from excess contours."""

    if len(candidates) <= config.max_piece_count:
        return candidates
    pool = sorted(
        candidates,
        key=lambda candidate: (
            candidate.area_error_ratio
            > config.artwork_hull_max_added_area_ratio,
            candidate.area_error_ratio,
            candidate.source_index,
        ),
    )[: config.max_visual_combination_candidates]
    best = min(
        combinations(pool, config.max_piece_count),
        key=lambda values: _piece_combination_score(values, config),
    )
    return sorted(best, key=lambda candidate: candidate.source_index)


def _build_card_puzzle(
    board: RectifiedBoard,
    *,
    layout: Literal["auto", "top-bottom", "left-right"],
    solver_config: SolverConfig,
    pattern_config: PatternConfig,
    image_path: str | None,
) -> CardPuzzleInput:
    divider = detect_divider(board, layout)
    fragments = detect_fragments(board, divider, solver_config)

    candidates: list[_VisualPieceCandidate] = []
    for source_index, fragment in enumerate(fragments):
        vertices = [
            (
                float(point[0]) / board.pixels_per_mm,
                float(point[1]) / board.pixels_per_mm,
            )
            for point in fragment.polygon_px
        ]
        piece = Piece(source_index, vertices)
        if min(edge.length for edge in piece.edges) < solver_config.image_min_edge_mm:
            continue
        candidates.append(_VisualPieceCandidate(source_index, piece, fragment))
    if not candidates:
        raise ValueError("detected contours did not produce usable polygons")

    selected = _select_best_piece_candidates(candidates, solver_config)
    selected_ids = {candidate.source_index for candidate in selected}
    discarded_candidate_ids = tuple(
        candidate.source_index
        for candidate in candidates
        if candidate.source_index not in selected_ids
    )
    observations = []
    for candidate in selected:
        observations.append(
            make_observation(
                candidate.piece,
                board.image_bgr,
                candidate.fragment.mask,
                board.pixels_per_mm,
                pattern_config,
            )
        )
    return CardPuzzleInput(
        observations=tuple(observations),
        rectified_bgr=board.image_bgr,
        paper_size_mm=(board.width_mm, board.height_mm),
        pixels_per_mm=board.pixels_per_mm,
        layout=divider.layout,
        divider_mm=divider.position_mm,
        image_path=image_path,
        detected_candidate_count=len(candidates),
        discarded_candidate_ids=discarded_candidate_ids,
    )


def load_card_puzzle(
    image_path: str | Path,
    *,
    layout: Literal["auto", "top-bottom", "left-right"] = "auto",
    solver_config: SolverConfig | None = None,
    pattern_config: PatternConfig | None = None,
) -> CardPuzzleInput:
    """Detect calibrated polygon geometry and retain every colour texture."""

    path = Path(image_path).expanduser().resolve()
    frame = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"cannot read image: {path}")
    active_solver = solver_config or SolverConfig()
    active_pattern = pattern_config or PatternConfig()
    board = detect_and_rectify_board(frame, active_solver)
    return _build_card_puzzle(
        board,
        layout=layout,
        solver_config=active_solver,
        pattern_config=active_pattern,
        image_path=str(path),
    )


def card_puzzle_from_rectified(
    rectified_bgr: np.ndarray,
    *,
    paper_size_mm: tuple[float, float] = (210.0, 297.0),
    pixels_per_mm: float = 5.0,
    layout: Literal["auto", "top-bottom", "left-right"] = "top-bottom",
    solver_config: SolverConfig | None = None,
    pattern_config: PatternConfig | None = None,
    image_path: str | None = None,
) -> CardPuzzleInput:
    """Build observations from an already calibrated A4 image."""

    if rectified_bgr is None or rectified_bgr.ndim != 3:
        raise ValueError("a rectified BGR colour image is required")
    if pixels_per_mm <= 0:
        raise ValueError("pixels_per_mm must be positive")
    width_mm, height_mm = (float(value) for value in paper_size_mm)
    board = RectifiedBoard(
        image_bgr=rectified_bgr,
        pixels_per_mm=float(pixels_per_mm),
        width_mm=width_mm,
        height_mm=height_mm,
        source_to_board_px=np.eye(3, dtype=np.float64),
    )
    return _build_card_puzzle(
        board,
        layout=layout,
        solver_config=solver_config or SolverConfig(),
        pattern_config=pattern_config or PatternConfig(),
        image_path=image_path,
    )
