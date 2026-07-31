"""Geometric pruning and final rectangle validation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Sequence

from shapely import set_precision
from shapely.geometry import LineString, MultiPoint, Polygon
from shapely.ops import unary_union

from .config import SolverConfig
from .geometry import Point, cross, polygon_corner_angles_deg, rectangle_dimensions
from .models import OpenEdge, PlacedPiece, SolverState


@dataclass(frozen=True)
class FinalValidation:
    """Detailed result of final assembly validation."""

    valid: bool
    reason: str
    short_side_mm: float | None = None
    long_side_mm: float | None = None
    rectangle: Polygon | None = None
    score: float | None = None
    official_dimensions_valid: bool | None = None


def check_length_match(first_length: float, second_length: float, tolerance: float) -> bool:
    """Compare edge lengths using a tolerance, never exact float equality."""

    return abs(first_length - second_length) <= tolerance


def check_vertex_distance(
    open_edge: OpenEdge,
    transformed_p1: Point,
    transformed_p2: Point,
    mapping: str,
    maximum_mm: float,
) -> tuple[bool, float]:
    """Check both paired endpoint distances for the selected correspondence."""

    if mapping == "direct":
        targets = (open_edge.p1, open_edge.p2)
    elif mapping == "reversed":
        targets = (open_edge.p2, open_edge.p1)
    else:
        raise ValueError(f"unknown endpoint mapping: {mapping}")
    distances = (
        math.dist(transformed_p1.as_tuple(), targets[0].as_tuple()),
        math.dist(transformed_p2.as_tuple(), targets[1].as_tuple()),
    )
    return (max(distances) <= maximum_mm, max(distances))


def check_correct_side(
    owner: PlacedPiece,
    open_edge: OpenEdge,
    candidate: PlacedPiece,
    candidate_edge: OpenEdge,
    tolerance: float,
) -> bool:
    """Require the two polygon interiors to lie on opposite edge sides.

    The sign of the 2-D cross product identifies the side of a directed
    line.  A tiny local interior probe is derived from each polygon's winding.
    This is more reliable than a centroid for concave polygons and supports
    both clockwise and counter-clockwise input.
    """

    def interior_probe(edge: OpenEdge, polygon: Polygon) -> Point:
        dx = edge.p2.x - edge.p1.x
        dy = edge.p2.y - edge.p1.y
        edge_length = math.hypot(dx, dy)
        winding_sign = 1.0 if polygon.exterior.is_ccw else -1.0
        probe_distance = max(1e-5, tolerance / max(edge_length, 1e-9))
        midpoint_x = (edge.p1.x + edge.p2.x) / 2.0
        midpoint_y = (edge.p1.y + edge.p2.y) / 2.0
        return Point(
            midpoint_x + winding_sign * (-dy / edge_length) * probe_distance,
            midpoint_y + winding_sign * (dx / edge_length) * probe_distance,
        )

    owner_point = interior_probe(open_edge, owner.polygon)
    candidate_point = interior_probe(candidate_edge, candidate.polygon)
    owner_side = cross(
        open_edge.p1,
        open_edge.p2,
        owner_point,
    )
    candidate_side = cross(
        open_edge.p1,
        open_edge.p2,
        candidate_point,
    )
    if abs(owner_side) <= tolerance or abs(candidate_side) <= tolerance:
        return False
    return owner_side * candidate_side < 0.0


def check_overlap(
    placed_pieces: Sequence[PlacedPiece],
    candidate: PlacedPiece,
    tolerance_mm2: float,
) -> tuple[bool, float]:
    """Reject positive-area intersections while allowing shared line edges."""

    maximum_intersection = 0.0
    for placed in placed_pieces:
        intersection_area = float(candidate.polygon.intersection(placed.polygon).area)
        maximum_intersection = max(maximum_intersection, intersection_area)
        if intersection_area > tolerance_mm2:
            return (False, maximum_intersection)
    return (True, maximum_intersection)


def check_bbox(
    placed_pieces: Sequence[PlacedPiece],
    candidate: PlacedPiece,
    config: SolverConfig,
) -> bool:
    """Prune assemblies whose oriented extent already exceeds target maxima."""

    coordinates: list[tuple[float, float]] = []
    for placed in (*placed_pieces, candidate):
        coordinates.extend(point.as_tuple() for point in placed.vertices)
    hull = MultiPoint(coordinates).convex_hull
    short_side, long_side, _ = rectangle_dimensions(hull)
    tolerance = max(config.length_tolerance_mm, config.bbox_tolerance_mm) + (
        config.geometry_tolerance_mm
    )
    return (
        short_side <= config.max_short_side_mm + tolerance
        and long_side <= config.max_long_side_mm + tolerance
    )


def _edge_on_rectangle_boundary(
    edge: OpenEdge,
    rectangle: Polygon,
    tolerance_mm: float,
) -> bool:
    """Check the whole segment, not merely one touching endpoint."""

    line = LineString([edge.p1.as_tuple(), edge.p2.as_tuple()])
    samples = [line.interpolate(fraction, normalized=True) for fraction in (0, 0.25, 0.5, 0.75, 1)]
    return all(sample.distance(rectangle.exterior) <= tolerance_mm for sample in samples)


def check_outer_edges(
    placed_pieces: Sequence[PlacedPiece],
    rectangle: Polygon,
    tolerance_mm: float,
) -> bool:
    """Require every fragment to contribute at least one complete outer edge."""

    return all(
        any(
            _edge_on_rectangle_boundary(edge, rectangle, tolerance_mm)
            for edge in placed.edges
        )
        for placed in placed_pieces
    )


def _parallel_angle_error_deg(first: tuple[float, float], second: tuple[float, float]) -> float:
    first_angle = math.atan2(first[1], first[0])
    second_angle = math.atan2(second[1], second[0])
    difference = abs(math.degrees(first_angle - second_angle)) % 180.0
    return min(difference, 180.0 - difference)


def check_final_rectangle(state: SolverState, config: SolverConfig) -> FinalValidation:
    """Run all final, tolerance-aware rectangle checks."""

    # Most terminal DFS states fail on dimensions or gross fill.  Both can be
    # rejected from vertices and source areas before constructing an expensive
    # Shapely union.  The later checks still revalidate exact union geometry.
    all_points = [
        point.as_tuple()
        for placed in state.placed_pieces
        for point in placed.vertices
    ]
    hull = MultiPoint(all_points).convex_hull
    short_side, long_side, rectangle = rectangle_dimensions(hull)
    if short_side <= 0 or long_side <= 0:
        return FinalValidation(False, "minimum rotated rectangle is degenerate")
    dimension_tolerance = config.rectangle_dimension_tolerance_mm
    if not (
        config.min_short_side_mm - dimension_tolerance
        <= short_side
        <= config.max_short_side_mm + dimension_tolerance
    ):
        return FinalValidation(False, "rectangle short side is outside the allowed range")
    if not (
        config.min_long_side_mm - dimension_tolerance
        <= long_side
        <= config.max_long_side_mm + dimension_tolerance
    ):
        return FinalValidation(False, "rectangle long side is outside the allowed range")

    raw_sum_piece_area = sum(placed.polygon.area for placed in state.placed_pieces)
    minimum_gap_area = max(0.0, float(rectangle.area - raw_sum_piece_area))
    minimum_gap_ratio = minimum_gap_area / max(float(rectangle.area), 1e-9)
    if minimum_gap_area > config.area_tolerance_mm2:
        return FinalValidation(False, "assembled area does not fill its rectangle")
    if (
        config.max_final_gap_ratio is not None
        and minimum_gap_ratio > config.max_final_gap_ratio
    ):
        return FinalValidation(False, "assembled rectangle gap ratio is too large")
    if (
        config.max_final_gap_area_mm2 is not None
        and minimum_gap_area > config.max_final_gap_area_mm2
    ):
        return FinalValidation(False, "assembled rectangle gap area is too large")

    # Independently rotated matching edges can differ by about 1e-14 mm.
    # Precision snapping prevents such invisible gaps from becoming a false
    # MultiPolygon while keeping the tolerance fully configuration-driven.
    polygons = [
        set_precision(placed.polygon, config.geometry_tolerance_mm)
        for placed in state.placed_pieces
    ]
    final_union = unary_union(polygons)
    if final_union.geom_type != "Polygon":
        return FinalValidation(False, "assembled pieces are not one connected polygon")
    if not final_union.is_valid:
        return FinalValidation(False, "assembled polygon is invalid")

    sum_piece_area = sum(polygon.area for polygon in polygons)
    overlap_area = sum_piece_area - final_union.area
    allowed_overlap = config.overlap_tolerance_mm2 * max(1, len(polygons) - 1)
    if overlap_area > allowed_overlap + config.geometry_tolerance_mm:
        return FinalValidation(False, "piece area and union area indicate overlap")

    if len(final_union.interiors) > 0:
        hole_area = sum(Polygon(interior).area for interior in final_union.interiors)
        if hole_area > config.area_tolerance_mm2:
            return FinalValidation(False, "assembled polygon has an internal hole")

    area_error = abs(float(rectangle.area - final_union.area))
    if area_error > config.area_tolerance_mm2:
        return FinalValidation(False, "assembled area does not fill its rectangle")
    rectangle_gap_area = max(0.0, float(rectangle.area - final_union.area))
    rectangle_gap_ratio = rectangle_gap_area / max(float(rectangle.area), 1e-9)
    if (
        config.max_final_gap_ratio is not None
        and rectangle_gap_ratio > config.max_final_gap_ratio
    ):
        return FinalValidation(False, "assembled rectangle gap ratio is too large")
    if (
        config.max_final_gap_area_mm2 is not None
        and rectangle_gap_area > config.max_final_gap_area_mm2
    ):
        return FinalValidation(False, "assembled rectangle gap area is too large")

    # Area alone accepts a narrow but deep missing corner.  This one-way
    # coverage check requires the fitted rectangle frame to be supported by
    # actual piece material while deliberately ignoring internal seams.
    if config.max_rectangle_boundary_gap_mm is not None:
        boundary_support = final_union.buffer(
            config.max_rectangle_boundary_gap_mm,
            join_style=2,
        )
        if not boundary_support.covers(rectangle.boundary):
            uncovered = rectangle.boundary.difference(boundary_support)
            return FinalValidation(
                False,
                "rectangle boundary has an unsupported segment "
                f"({uncovered.length:.3f} mm outside tolerance)",
            )

    simplified = final_union.simplify(
        max(config.geometry_tolerance_mm, config.outer_edge_tolerance_mm),
        preserve_topology=True,
    )
    corners = list(simplified.exterior.coords)[:-1]
    if len(corners) != 4:
        if not config.allow_fitted_rectangle:
            return FinalValidation(False, "outer boundary is not close to four-sided")
    else:
        corner_angles = polygon_corner_angles_deg(simplified)
        if any(abs(angle - 90.0) > config.angle_tolerance_deg for angle in corner_angles):
            return FinalValidation(False, "outer boundary has a non-right corner")

        vectors = [
            (
                corners[(index + 1) % 4][0] - corners[index][0],
                corners[(index + 1) % 4][1] - corners[index][1],
            )
            for index in range(4)
        ]
        if (
            _parallel_angle_error_deg(vectors[0], vectors[2]) > config.angle_tolerance_deg
            or _parallel_angle_error_deg(vectors[1], vectors[3]) > config.angle_tolerance_deg
        ):
            return FinalValidation(False, "opposite outer edges are not parallel")

    if not check_outer_edges(
        state.placed_pieces,
        rectangle,
        config.outer_edge_tolerance_mm,
    ):
        return FinalValidation(False, "at least one piece has no outer rectangle edge")

    dimension_midpoint_error = abs(
        short_side - (config.min_short_side_mm + config.max_short_side_mm) / 2.0
    ) + abs(long_side - (config.min_long_side_mm + config.max_long_side_mm) / 2.0)
    score = area_error + 0.01 * dimension_midpoint_error
    official_tolerance = config.official_dimension_tolerance_mm
    official_dimensions_valid = (
        config.min_short_side_mm - official_tolerance
        <= short_side
        <= config.max_short_side_mm + official_tolerance
        and config.min_long_side_mm - official_tolerance
        <= long_side
        <= config.max_long_side_mm + official_tolerance
    )
    return FinalValidation(
        True,
        "valid rectangle",
        short_side_mm=short_side,
        long_side_mm=long_side,
        rectangle=rectangle,
        score=score,
        official_dimensions_valid=official_dimensions_valid,
    )
