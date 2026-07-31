"""Public adapter from a colour photograph to standalone Q3 observations."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from .config import PatternConfig, SolverConfig
from .edge_features import make_observation
from .models import CardPuzzleInput, Piece
from .piece_detection import (
    RectifiedBoard,
    detect_and_rectify_board,
    detect_divider,
    detect_fragments,
)


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

    observations = []
    for piece_id, fragment in enumerate(fragments):
        vertices = [
            (
                float(point[0]) / board.pixels_per_mm,
                float(point[1]) / board.pixels_per_mm,
            )
            for point in fragment.polygon_px
        ]
        piece = Piece(piece_id, vertices)
        if min(edge.length for edge in piece.edges) < solver_config.image_min_edge_mm:
            continue
        observations.append(
            make_observation(
                piece,
                board.image_bgr,
                fragment.mask,
                board.pixels_per_mm,
                pattern_config,
            )
        )
    if not observations:
        raise ValueError("detected contours did not produce usable polygons")
    if len(observations) > solver_config.max_piece_count:
        raise ValueError("more than four usable fragments were detected")
    return CardPuzzleInput(
        observations=tuple(observations),
        rectified_bgr=board.image_bgr,
        paper_size_mm=(board.width_mm, board.height_mm),
        pixels_per_mm=board.pixels_per_mm,
        layout=divider.layout,
        divider_mm=divider.position_mm,
        image_path=image_path,
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
