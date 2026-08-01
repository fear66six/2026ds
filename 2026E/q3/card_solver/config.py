"""Configuration for the standalone playing-card fragment solver.

Distances are millimetres and areas are square millimetres throughout Q3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverConfig:
    """Geometry, image and search tolerances."""

    max_piece_count: int = 4
    # A strongly supported colour hypothesis may remove an opposite-suit
    # distractor first; the complete fragment set remains the fallback.
    allow_distractor_pieces: bool = True
    min_vertices: int = 3
    max_vertices: int = 5
    min_physical_edge_mm: float = 20.0
    image_min_edge_mm: float = 8.0
    length_tolerance_mm: float = 4.0
    max_vertex_distance_mm: float = 20.0
    overlap_tolerance_mm2: float = 12.0
    max_overlap_sliver_width_mm: float = 3.5
    max_overlap_sliver_area_mm2: float = 90.0
    geometry_tolerance_mm: float = 1e-5
    bbox_tolerance_mm: float = 12.0

    min_long_side_mm: float = 90.0
    max_long_side_mm: float = 120.0
    image_min_long_side_mm: float = 80.0
    min_short_side_mm: float = 50.0
    max_short_side_mm: float = 90.0
    rectangle_dimension_tolerance_mm: float = 5.0
    outer_edge_tolerance_mm: float = 3.0
    max_final_gap_ratio: float = 0.08
    max_final_gap_area_mm2: float = 600.0
    max_rectangle_boundary_gap_mm: float = 3.5
    connection_gap_tolerance_mm: float = 2.0

    allow_partial_edge_matches: bool = True
    enable_expanded_length_search: bool = True
    approximate_full_match_tolerance_mm: float = 8.0
    enable_rectangular_grid_search: bool = True
    enable_rectangular_strip_search: bool = True
    grid_max_corner_error_deg: float = 15.0
    grid_min_rectangle_fill_ratio: float = 0.85
    grid_max_piece_area_ratio: float = 1.50
    strip_min_aspect_ratio: float = 1.80
    partial_min_residual_mm: float = 18.0
    min_connection_length_mm: float = 6.0
    find_best_solution: bool = True
    # Image search is bounded by wall-clock time rather than an arbitrary
    # traversal count.  Optional count limits remain available for tests and
    # diagnostics, but production defaults do not discard a solvable branch
    # merely because it was reached after a fixed number of candidates.
    max_search_nodes: int | None = None
    max_candidate_attempts: int | None = None
    max_search_seconds: float | None = 60.0
    return_best_effort_on_timeout: bool = True
    best_solution_stop_gap_ratio: float = 0.06
    best_solution_stop_pattern_error: float = 0.40
    best_solution_stop_pattern_confidence: float = 0.10
    best_solution_stop_corner_error: float = 1.0
    best_solution_stop_symmetry_error: float = 0.18

    weight_length: float = 4.0
    weight_vertex: float = 1.0
    weight_shape: float = 0.3
    weight_pattern: float = 45.0
    weight_corner_layout: float = 30.0
    weight_symmetry: float = 80.0
    irregular_geometry_weight: float = 100.0
    irregular_pattern_weight: float = 1.0
    pattern_confidence_reward: float = 0.45
    pattern_uncertainty_penalty: float = 0.60

    signature_position_precision: int = 2
    signature_rotation_precision: int = 4
    base_right_angle_tolerance_deg: float = 10.0

    canonical_pixels_per_mm: float = 5.0
    min_piece_area_mm2: float = 180.0
    max_piece_area_mm2: float = 8_500.0
    polygon_area_error_ratio: float = 0.12
    quadrilateral_area_error_ratio: float = 0.16
    artwork_hull_max_added_area_ratio: float = 0.25
    artwork_hull_min_ink_support_ratio: float = 0.65
    artwork_dark_gray_threshold: int = 20
    # Black suit artwork is part of the physical paper even though it is not
    # included in the white-stock seed.  Estimate the dark board colour and
    # retain nearby pixels whose BGR distance is clearly outside its noise.
    artwork_background_min_color_distance: float = 30.0
    artwork_background_noise_percentile: float = 90.0
    artwork_background_noise_multiplier: float = 1.5
    artwork_support_distance_mm: float = 1.0
    divider_exclusion_mm: float = 3.0
    max_visual_combination_candidates: int = 12

    merge_collinear_open_edges: bool = True
    open_edge_merge_angle_tolerance_deg: float = 3.0
    open_edge_merge_distance_tolerance_mm: float = 1.0

    def __post_init__(self) -> None:
        if self.max_piece_count < 1:
            raise ValueError("max_piece_count must be positive")
        if self.min_vertices < 3 or self.max_vertices < self.min_vertices:
            raise ValueError("invalid polygon vertex limits")
        if self.min_short_side_mm > self.max_short_side_mm:
            raise ValueError("short-side minimum exceeds maximum")
        if self.min_long_side_mm > self.max_long_side_mm:
            raise ValueError("long-side minimum exceeds maximum")
        if self.image_min_long_side_mm > self.max_long_side_mm:
            raise ValueError("image long-side minimum exceeds maximum")
        if self.approximate_full_match_tolerance_mm < self.length_tolerance_mm:
            raise ValueError(
                "approximate full-match tolerance is below length tolerance"
            )
        if not 0.0 <= self.artwork_background_noise_percentile <= 100.0:
            raise ValueError("artwork background percentile must be between zero and 100")
        if not 0.0 <= self.max_final_gap_ratio <= 1.0:
            raise ValueError("max_final_gap_ratio must be between zero and one")
        for name in ("max_search_nodes", "max_candidate_attempts"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive when configured")
        if self.max_search_seconds is not None and self.max_search_seconds <= 0.0:
            raise ValueError("max_search_seconds must be positive when configured")
        if self.max_visual_combination_candidates < self.max_piece_count:
            raise ValueError(
                "max_visual_combination_candidates is below max_piece_count"
            )
        for name, value in vars(self).items():
            if isinstance(value, (int, float)) and name not in {
                "signature_position_precision",
                "signature_rotation_precision",
            } and value < 0:
                raise ValueError(f"{name} must be non-negative")


def production_solver_config() -> SolverConfig:
    """Return bounded defaults for the at-most-four-piece production path."""

    return SolverConfig(
        find_best_solution=False,
        max_search_nodes=None,
        max_search_seconds=60.0,
        return_best_effort_on_timeout=True,
        enable_expanded_length_search=True,
    )


@dataclass(frozen=True)
class PatternConfig:
    """Parameters used to sample and compare a cut-edge texture."""

    sample_step_mm: float = 0.5
    endpoint_margin_mm: float = 1.0
    first_sample_depth_mm: float = 0.25
    strip_depth_mm: float = 5.0
    depth_samples: int = 8
    profile_smoothing_mm: float = 0.8

    weight_color: float = 0.45
    weight_foreground: float = 0.30
    weight_line: float = 0.25
    min_informative_confidence: float = 0.10
    # Intermediate DFS seams can be sampled before all neighbouring slivers
    # are resolved.  Keep this looser than the strict final seam threshold so
    # a globally correct card is not pruned before final revalidation.
    hard_reject_error: float = 0.70
    final_reject_error: float = 0.55
    reject_full_confidence: float = 0.20
    low_confidence_error_allowance: float = 0.20

    suit_min_ink_area_mm2: float = 20.0
    suit_dominance_ratio: float = 3.0

    white_lightness_threshold: float = 72.0
    black_lightness_threshold: float = 38.0
    red_a_threshold: float = 145.0

    # A standard card index is a rank plus a small suit near each of two
    # opposite card corners.  These component limits exclude the larger centre
    # pips while retaining both red and black corner indices.
    corner_search_radius_mm: float = 18.0
    corner_group_distance_mm: float = 18.0
    corner_boundary_exclusion_mm: float = 0.8
    corner_min_component_area_mm2: float = 2.0
    corner_max_component_area_mm2: float = 75.0
    # Recovery from an oversized face-art component graph is intentionally
    # stricter than ordinary marker extraction.  Both the rank and suit of a
    # real corner index remain substantial components; tiny illustration
    # details must not be combined into synthetic Joker indices.
    corner_recovered_min_component_area_mm2: float = 20.0
    corner_min_local_area_mm2: float = 0.35
    corner_min_components: int = 2
    corner_max_components: int = 3
    corner_layout_tolerance_mm: float = 34.0
    corner_direction_min_separation_mm: float = 2.0
    corner_chirality_min_abs: float = 0.05
    corner_direction_area_flip_ratio: float = 1.15
    corner_same_piece_min_diagonal_ratio: float = 0.60

    symmetry_pixels_per_mm: float = 1.5
    symmetry_corner_exclusion_mm: float = 0.0
    symmetry_match_tolerance_mm: float = 2.0
    symmetry_min_foreground_area_mm2: float = 80.0
    max_final_symmetry_error: float = 0.25

    def __post_init__(self) -> None:
        if self.sample_step_mm <= 0 or self.strip_depth_mm <= 0:
            raise ValueError("texture sampling dimensions must be positive")
        if self.depth_samples < 2:
            raise ValueError("depth_samples must be at least two")
        if not 0.0 <= self.min_informative_confidence <= 1.0:
            raise ValueError("invalid pattern confidence threshold")
        if self.hard_reject_error < 0 or self.final_reject_error < 0:
            raise ValueError("pattern error thresholds must be non-negative")
        if self.reject_full_confidence < self.min_informative_confidence:
            raise ValueError("reject_full_confidence is below informative confidence")
        if self.corner_min_components < 2:
            raise ValueError("corner_min_components must be at least two")
        if self.corner_max_components < self.corner_min_components:
            raise ValueError("corner_max_components is below corner_min_components")
        if self.corner_min_component_area_mm2 > self.corner_max_component_area_mm2:
            raise ValueError("invalid corner component area limits")
        if not (
            self.corner_min_component_area_mm2
            <= self.corner_recovered_min_component_area_mm2
            <= self.corner_max_component_area_mm2
        ):
            raise ValueError("invalid recovered corner component area limit")
        if self.corner_direction_area_flip_ratio < 1.0:
            raise ValueError("corner direction area flip ratio must be at least one")
        if not 0.0 <= self.corner_same_piece_min_diagonal_ratio <= 1.0:
            raise ValueError("corner same-piece diagonal ratio is outside zero to one")
