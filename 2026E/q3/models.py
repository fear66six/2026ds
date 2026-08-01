"""Serializable Q3 scene models."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CardPieceState:
    piece_id: int
    vertices_mm: np.ndarray
    center_mm: tuple[float, float]
    area_mm2: float
    red_ink_area_mm2: float
    black_ink_area_mm2: float


@dataclass
class CardScene:
    cycle_index: int
    image_path: str
    pieces: list[CardPieceState]
    layout: str | None
    divider_mm: float | None
    paper_valid: bool
    scene_valid: bool
    solution_success: bool
    used_piece_ids: list[int] = field(default_factory=list)
    ignored_piece_ids: list[int] = field(default_factory=list)
    rectangle_size_mm: tuple[float, float] | None = None
    geometry_score: float | None = None
    pattern_score: float | None = None
    pattern_confidence: float | None = None
    corner_layout_score: float | None = None
    corner_layout_confidence: float | None = None
    symmetry_score: float | None = None
    symmetry_confidence: float | None = None
    best_effort: bool = False
    detected_candidate_count: int = 0
    discarded_candidate_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)
