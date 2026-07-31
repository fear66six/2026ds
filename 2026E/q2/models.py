"""Serializable Q2 scene models."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class WhitePieceState:
    piece_id: int
    vertices_mm: np.ndarray
    center_mm: tuple[float, float]
    area_mm2: float


@dataclass
class WhitePuzzleScene:
    cycle_index: int
    image_path: str
    pieces: list[WhitePieceState]
    divider_y_mm: float | None
    paper_valid: bool
    scene_valid: bool
    solution_success: bool
    exact_solution: bool
    official_dimensions_valid: bool | None
    best_effort: bool = False
    rectangle_size_mm: tuple[float, float] | None = None
    solution_score: float | None = None
    detected_candidate_count: int = 0
    warnings: list[str] = field(default_factory=list)
    solver_stats: dict[str, float | int | bool | str | None] = field(
        default_factory=dict
    )
    timings_ms: dict[str, float] = field(default_factory=dict)

