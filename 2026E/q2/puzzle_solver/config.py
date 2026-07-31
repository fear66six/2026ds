"""Configuration for the geometric puzzle solver.

All distances are expressed in millimetres and all areas in square
millimetres.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SolverConfig:
    """Numerical tolerances and search scoring weights."""

    max_piece_count: int = 4
    min_edge_length_mm: float = 20.0
    length_tolerance_mm: float = 1.5
    max_vertex_distance_mm: float = 20.0
    angle_tolerance_deg: float = 3.0
    outer_edge_tolerance_mm: float = 2.0
    overlap_tolerance_mm2: float = 0.5
    area_tolerance_mm2: float = 8.0
    max_final_gap_ratio: float | None = None
    max_final_gap_area_mm2: float | None = None
    side_tolerance_mm2: float = 1e-7
    geometry_tolerance_mm: float = 1e-6
    bbox_tolerance_mm: float = 2.0
    rectangle_dimension_tolerance_mm: float = 0.0
    official_dimension_tolerance_mm: float = 0.0
    max_rectangle_boundary_gap_mm: float | None = None

    max_long_side_mm: float = 120.0
    min_long_side_mm: float = 90.0
    max_short_side_mm: float = 90.0
    min_short_side_mm: float = 50.0

    weight_length: float = 4.0
    weight_vertex: float = 1.0
    weight_shape: float = 0.25

    base_right_angle_tolerance_deg: float = 8.0
    base_area_weight: float = 1.0
    base_right_angle_weight: float = 50.0
    base_longest_edge_weight: float = 1.0

    signature_position_precision: int = 3
    signature_rotation_precision: int = 5
    allow_fitted_rectangle: bool = False
    allow_partial_edge_matches: bool = True
    partial_min_residual_mm: float = 20.0
    merge_collinear_open_edges: bool = True
    open_edge_merge_angle_tolerance_deg: float = 3.0
    open_edge_merge_distance_tolerance_mm: float = 1.0
    find_best_solution: bool = False
    best_solution_stop_area_ratio: float | None = None
    enable_expanded_length_search: bool = True
    approximate_full_match_tolerance_mm: float = 10.0
    min_connection_length_mm: float = 8.0
    max_search_nodes: int | None = None
    max_candidate_attempts: int | None = None
    max_search_seconds: float | None = 60.0
    return_best_effort_on_failure: bool = False

    def __post_init__(self) -> None:
        non_negative = (
            "length_tolerance_mm",
            "min_edge_length_mm",
            "max_vertex_distance_mm",
            "angle_tolerance_deg",
            "outer_edge_tolerance_mm",
            "overlap_tolerance_mm2",
            "area_tolerance_mm2",
            "geometry_tolerance_mm",
            "bbox_tolerance_mm",
            "rectangle_dimension_tolerance_mm",
            "official_dimension_tolerance_mm",
            "partial_min_residual_mm",
            "approximate_full_match_tolerance_mm",
            "min_connection_length_mm",
            "open_edge_merge_angle_tolerance_deg",
            "open_edge_merge_distance_tolerance_mm",
        )
        for name in non_negative:
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.min_short_side_mm > self.max_short_side_mm:
            raise ValueError("short-side minimum exceeds maximum")
        if self.min_long_side_mm > self.max_long_side_mm:
            raise ValueError("long-side minimum exceeds maximum")
        if self.max_piece_count < 1:
            raise ValueError("max_piece_count must be positive")
        if (
            self.max_final_gap_ratio is not None
            and not 0.0 <= self.max_final_gap_ratio <= 1.0
        ):
            raise ValueError("max_final_gap_ratio must be between zero and one")
        if (
            self.max_final_gap_area_mm2 is not None
            and self.max_final_gap_area_mm2 < 0.0
        ):
            raise ValueError("max_final_gap_area_mm2 must be non-negative")
        if (
            self.best_solution_stop_area_ratio is not None
            and not 0.0 <= self.best_solution_stop_area_ratio <= 1.0
        ):
            raise ValueError("best_solution_stop_area_ratio must be between zero and one")
        if (
            self.max_rectangle_boundary_gap_mm is not None
            and self.max_rectangle_boundary_gap_mm < 0.0
        ):
            raise ValueError("max_rectangle_boundary_gap_mm must be non-negative")
        if (
            self.approximate_full_match_tolerance_mm
            < self.length_tolerance_mm
        ):
            raise ValueError(
                "approximate_full_match_tolerance_mm must not be below "
                "length_tolerance_mm"
            )
        for name in ("max_search_nodes", "max_candidate_attempts"):
            value = getattr(self, name)
            if value is not None and value < 1:
                raise ValueError(f"{name} must be positive when configured")
        if self.max_search_seconds is not None and self.max_search_seconds <= 0.0:
            raise ValueError("max_search_seconds must be positive when configured")
