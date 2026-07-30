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
    side_tolerance_mm2: float = 1e-7
    geometry_tolerance_mm: float = 1e-6
    bbox_tolerance_mm: float = 2.0
    rectangle_dimension_tolerance_mm: float = 0.0

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
    find_best_solution: bool = False
    best_solution_stop_area_ratio: float | None = None

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
            "partial_min_residual_mm",
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
            self.best_solution_stop_area_ratio is not None
            and not 0.0 <= self.best_solution_stop_area_ratio <= 1.0
        ):
            raise ValueError("best_solution_stop_area_ratio must be between zero and one")
