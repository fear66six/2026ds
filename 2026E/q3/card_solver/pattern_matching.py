"""Confidence-aware matching of two texture-bearing cut edges."""

from __future__ import annotations

import math

import numpy as np

from .config import PatternConfig
from .geometry import Point
from .models import PieceObservation, PlacedPiece, SeamScore


def _project_source_position(
    placed: PlacedPiece,
    edge_id: int,
    world_points: list[Point],
) -> np.ndarray:
    edge = placed.source_piece.edges[edge_id]
    dx = (edge.p2.x - edge.p1.x) / edge.length
    dy = (edge.p2.y - edge.p1.y) / edge.length
    source = [placed.transform.inverse_apply(point) for point in world_points]
    return np.asarray(
        [(point.x - edge.p1.x) * dx + (point.y - edge.p1.y) * dy for point in source],
        dtype=np.float32,
    )


def _linear(feature_x: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    if values.ndim == 1:
        return np.interp(query, feature_x, values).astype(np.float32)
    return np.column_stack(
        [np.interp(query, feature_x, values[:, column]) for column in range(values.shape[1])]
    ).astype(np.float32)


def _nearest(feature_x: np.ndarray, values: np.ndarray, query: np.ndarray) -> np.ndarray:
    indices = np.searchsorted(feature_x, query, side="left")
    indices = np.clip(indices, 0, len(feature_x) - 1)
    previous = np.clip(indices - 1, 0, len(feature_x) - 1)
    use_previous = np.abs(feature_x[previous] - query) < np.abs(feature_x[indices] - query)
    indices[use_previous] = previous[use_previous]
    return values[indices]


class PatternMatcher:
    """Compare cached profiles at the physical overlap of two placed edges."""

    def __init__(
        self,
        observations: dict[int, PieceObservation],
        config: PatternConfig | None = None,
    ) -> None:
        self.observations = observations
        self.config = config or PatternConfig()

    def score(
        self,
        first: PlacedPiece,
        first_edge_id: int,
        second: PlacedPiece,
        second_edge_id: int,
        p1: Point,
        p2: Point,
    ) -> SeamScore:
        length = math.dist(p1.as_tuple(), p2.as_tuple())
        empty = SeamScore(
            first.piece_id,
            first_edge_id,
            second.piece_id,
            second_edge_id,
            p1,
            p2,
            0.0,
            0.0,
        )
        if length <= self.config.sample_step_mm:
            return empty
        first_observation = self.observations.get(first.piece_id)
        second_observation = self.observations.get(second.piece_id)
        if first_observation is None or second_observation is None:
            return empty
        feature_a = first_observation.edge_features.get(first_edge_id)
        feature_b = second_observation.edge_features.get(second_edge_id)
        if feature_a is None or feature_b is None:
            return empty

        count = max(6, int(round(length / self.config.sample_step_mm)) + 1)
        fractions = np.linspace(0.0, 1.0, count)
        world = [
            Point(p1.x + (p2.x - p1.x) * t, p1.y + (p2.y - p1.y) * t)
            for t in fractions
        ]
        positions_a = _project_source_position(first, first_edge_id, world)
        positions_b = _project_source_position(second, second_edge_id, world)
        inside_a = (positions_a >= feature_a.positions_mm[0]) & (
            positions_a <= feature_a.positions_mm[-1]
        )
        inside_b = (positions_b >= feature_b.positions_mm[0]) & (
            positions_b <= feature_b.positions_mm[-1]
        )
        valid_a = _nearest(feature_a.positions_mm, feature_a.valid, positions_a)
        valid_b = _nearest(feature_b.positions_mm, feature_b.valid, positions_b)
        valid = inside_a & inside_b & valid_a & valid_b
        if np.count_nonzero(valid) < 4:
            return empty

        lab_a = _linear(feature_a.positions_mm, feature_a.lab, positions_a)
        lab_b = _linear(feature_b.positions_mm, feature_b.lab, positions_b)
        classes_a = _nearest(feature_a.positions_mm, feature_a.classes, positions_a)
        classes_b = _nearest(feature_b.positions_mm, feature_b.classes, positions_b)
        lines_a = _linear(feature_a.positions_mm, feature_a.line_profile, positions_a)
        lines_b = _linear(feature_b.positions_mm, feature_b.line_profile, positions_b)
        info_a = _linear(feature_a.positions_mm, feature_a.information, positions_a)
        info_b = _linear(feature_b.positions_mm, feature_b.information, positions_b)

        information = np.maximum(info_a, info_b)
        weights = np.where(valid, np.maximum(information, 0.03), 0.0)
        weight_sum = float(np.sum(weights))
        if weight_sum <= 1e-8:
            return empty

        color_error = np.clip(np.linalg.norm(lab_a - lab_b, axis=1) / 100.0, 0.0, 1.0)
        foreground_error = (classes_a != classes_b).astype(np.float32)
        line_error = np.abs(lines_a - lines_b)
        combined = (
            self.config.weight_color * color_error
            + self.config.weight_foreground * foreground_error
            + self.config.weight_line * line_error
        )
        error = float(np.sum(combined * weights) / weight_sum)
        confidence = float(np.mean(information[valid]) * np.mean(valid))
        return SeamScore(
            first.piece_id,
            first_edge_id,
            second.piece_id,
            second_edge_id,
            p1,
            p2,
            error,
            min(1.0, max(0.0, confidence)),
        )

    def rejects(self, seam: SeamScore, final: bool = False) -> bool:
        threshold = (
            self.config.final_reject_error if final else self.config.hard_reject_error
        )
        confidence_span = max(
            self.config.reject_full_confidence
            - self.config.min_informative_confidence,
            1e-9,
        )
        uncertainty = np.clip(
            (self.config.reject_full_confidence - seam.confidence)
            / confidence_span,
            0.0,
            1.0,
        )
        # A weak near-white strip is useful for candidate ordering but is not
        # reliable enough to veto a topology by itself.  As confidence grows,
        # the original strict mismatch threshold is restored continuously.
        threshold += self.config.low_confidence_error_allowance * float(uncertainty)
        return (
            seam.confidence >= self.config.min_informative_confidence
            and seam.error > threshold
        )
