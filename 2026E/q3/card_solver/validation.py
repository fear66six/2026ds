"""Geometry and terminal seam validation for the standalone Q3 solver."""

from __future__ import annotations

from dataclasses import dataclass
import itertools
import math
from typing import Iterable, Mapping, Sequence

import cv2
import numpy as np
from shapely.geometry import (
    GeometryCollection,
    LineString,
    MultiLineString,
    MultiPoint,
    Point as ShapelyPoint,
    Polygon,
)
from shapely.ops import unary_union

from .config import PatternConfig, SolverConfig
from .geometry import Point, cross, polygon_angles_deg
from .models import OpenEdge, Piece, PieceObservation, PlacedPiece, SeamScore, SolverState
from .pattern_matching import PatternMatcher


@dataclass(frozen=True)
class FinalValidation:
    valid: bool
    reason: str | None = None
    rectangle: Polygon | None = None
    long_side_mm: float | None = None
    short_side_mm: float | None = None
    geometry_score: float | None = None
    pattern_score: float = 0.0
    pattern_confidence: float = 0.0
    corner_layout_score: float = 0.0
    corner_layout_confidence: float = 0.0
    symmetry_score: float = 0.0
    symmetry_confidence: float = 0.0
    strict_global_pattern: bool = False
    seams: tuple[SeamScore, ...] = ()


def is_uniform_rectangular_grid(
    pieces: Sequence[Piece],
    config: SolverConfig,
) -> bool:
    """Return whether four similar rectangular quarters need strict texture checks."""

    return (
        config.enable_rectangular_grid_search
        and len(pieces) == 4
        and uses_global_pattern_constraints(pieces, config)
    )


def uses_global_pattern_constraints(
    pieces: Sequence[Piece],
    config: SolverConfig,
) -> bool:
    """Return whether similar rectangular fragments need whole-card checks.

    Uniform rectangular cuts are geometrically ambiguous: several strip or
    grid permutations form the same outer rectangle.  Seam texture, corner
    indices and whole-card symmetry must therefore rank every valid assembly.
    Irregular cuts remain geometry-dominant because their unique cut edges are
    stronger evidence than potentially noisy artwork segmentation.
    """

    if (
        not 2 <= len(pieces) <= config.max_piece_count
        or any(len(piece.vertices) != 4 for piece in pieces)
    ):
        return False
    areas = [piece.area for piece in pieces]
    if min(areas) <= 1e-9 or max(areas) / min(areas) > config.grid_max_piece_area_ratio:
        return False
    for piece in pieces:
        if any(
            abs(angle - 90.0) > config.grid_max_corner_error_deg
            for angle in polygon_angles_deg(piece.polygon)
        ):
            return False
        rectangle_area = float(piece.polygon.minimum_rotated_rectangle.area)
        if (
            rectangle_area <= 1e-9
            or piece.area / rectangle_area < config.grid_min_rectangle_fill_ratio
        ):
            return False
    return True


def is_uniform_rectangular_strips(
    pieces: Sequence[Piece],
    config: SolverConfig,
) -> bool:
    """Return whether similar elongated rectangles form a strip puzzle."""

    if (
        not config.enable_rectangular_strip_search
        or not uses_global_pattern_constraints(pieces, config)
    ):
        return False
    for piece in pieces:
        rectangle = piece.polygon.minimum_rotated_rectangle
        coordinates = list(rectangle.exterior.coords)[:-1]
        lengths = [
            math.dist(coordinates[index], coordinates[(index + 1) % 4])
            for index in range(4)
        ]
        short_side, long_side = min(lengths), max(lengths)
        if (
            short_side <= config.geometry_tolerance_mm
            or long_side / short_side < config.strip_min_aspect_ratio
        ):
            return False
    return True


def check_length_match(first: float, second: float, tolerance: float) -> bool:
    return abs(first - second) <= tolerance


def check_correct_side(
    owner: PlacedPiece,
    edge: OpenEdge,
    candidate: PlacedPiece,
    tolerance: float,
) -> bool:
    direction = Point(edge.p2.x - edge.p1.x, edge.p2.y - edge.p1.y)
    owner_offset = Point(
        owner.centroid.x - edge.p1.x,
        owner.centroid.y - edge.p1.y,
    )
    candidate_offset = Point(
        candidate.centroid.x - edge.p1.x,
        candidate.centroid.y - edge.p1.y,
    )
    owner_side = cross(direction, owner_offset)
    candidate_side = cross(direction, candidate_offset)
    if abs(owner_side) <= tolerance or abs(candidate_side) <= tolerance:
        return False
    return owner_side * candidate_side < 0.0


def check_overlap(
    placed: Iterable[PlacedPiece],
    candidate: PlacedPiece,
    config: SolverConfig,
    *,
    allow_sliver: bool = True,
) -> tuple[bool, float]:
    largest = 0.0
    for item in placed:
        intersection = item.polygon.intersection(candidate.polygon)
        area = float(intersection.area)
        largest = max(largest, area)
        if area <= config.overlap_tolerance_mm2:
            continue
        if not allow_sliver:
            return False, area
        if area > config.max_overlap_sliver_area_mm2 or intersection.is_empty:
            return False, area
        rectangle = intersection.minimum_rotated_rectangle
        if not isinstance(rectangle, Polygon):
            return False, area
        short_side, _ = _rectangle_dimensions(rectangle)
        if short_side > config.max_overlap_sliver_width_mm:
            return False, area
    # A shared boundary has zero intersection area and is intentionally valid.
    return True, largest


def _rectangle_dimensions(rectangle: Polygon) -> tuple[float, float]:
    coordinates = list(rectangle.exterior.coords)[:-1]
    lengths = [
        math.dist(coordinates[index], coordinates[(index + 1) % len(coordinates)])
        for index in range(len(coordinates))
    ]
    unique = sorted(lengths)
    return (0.5 * (unique[0] + unique[1]), 0.5 * (unique[-1] + unique[-2]))


def check_bbox(
    current: Iterable[PlacedPiece],
    candidate: PlacedPiece,
    config: SolverConfig,
) -> bool:
    points = [
        point.as_tuple()
        for placed in [*current, candidate]
        for point in placed.vertices
    ]
    rectangle = MultiPoint(points).minimum_rotated_rectangle
    if not isinstance(rectangle, Polygon):
        return False
    short_side, long_side = _rectangle_dimensions(rectangle)
    tolerance = config.bbox_tolerance_mm
    return (
        short_side <= config.max_short_side_mm + tolerance
        and long_side <= config.max_long_side_mm + tolerance
    )


def _line_parts(geometry: object) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    if isinstance(geometry, GeometryCollection):
        output: list[LineString] = []
        for item in geometry.geoms:
            output.extend(_line_parts(item))
        return output
    return []


def _edge_for_segment(placed: PlacedPiece, segment: LineString) -> int | None:
    midpoint = segment.interpolate(0.5, normalized=True)
    best_id: int | None = None
    best_distance = math.inf
    for edge in placed.edges:
        line = LineString([edge.p1.as_tuple(), edge.p2.as_tuple()])
        distance = max(
            line.distance(midpoint),
            line.distance(segment.boundary.geoms[0]),
            line.distance(segment.boundary.geoms[-1]),
        )
        if distance < best_distance:
            best_distance = distance
            best_id = edge.edge_id
    return best_id if best_distance <= 1e-3 else None


def discover_and_score_seams(
    pieces: list[PlacedPiece],
    matcher: PatternMatcher,
    config: SolverConfig,
    pattern_config: PatternConfig,
    *,
    enforce_rejection: bool = True,
) -> tuple[tuple[SeamScore, ...], str | None]:
    """Find and score every physical contact in the completed assembly."""

    seams: list[SeamScore] = []

    def contact_segment(first_edge: OpenEdge, second_edge: OpenEdge) -> tuple[Point, Point] | None:
        first_dx = (first_edge.p2.x - first_edge.p1.x) / first_edge.length
        first_dy = (first_edge.p2.y - first_edge.p1.y) / first_edge.length
        second_dx = (second_edge.p2.x - second_edge.p1.x) / second_edge.length
        second_dy = (second_edge.p2.y - second_edge.p1.y) / second_edge.length
        if abs(first_dx * second_dy - first_dy * second_dx) > math.sin(math.radians(6.0)):
            return None

        def normal_distance(point: Point) -> float:
            return abs(
                first_dx * (point.y - first_edge.p1.y)
                - first_dy * (point.x - first_edge.p1.x)
            )

        if max(normal_distance(second_edge.p1), normal_distance(second_edge.p2)) > config.length_tolerance_mm:
            return None
        projections = [
            (point.x - first_edge.p1.x) * first_dx
            + (point.y - first_edge.p1.y) * first_dy
            for point in (second_edge.p1, second_edge.p2)
        ]
        start = max(0.0, min(projections))
        end = min(first_edge.length, max(projections))
        if end - start < config.min_connection_length_mm:
            return None
        return (
            Point(first_edge.p1.x + start * first_dx, first_edge.p1.y + start * first_dy),
            Point(first_edge.p1.x + end * first_dx, first_edge.p1.y + end * first_dy),
        )

    for first_index, first in enumerate(pieces):
        for second in pieces[first_index + 1 :]:
            contacts: list[tuple[int, int, Point, Point]] = []
            for first_edge in first.edges:
                for second_edge in second.edges:
                    segment = contact_segment(first_edge, second_edge)
                    if segment is not None:
                        contacts.append(
                            (first_edge.edge_id, second_edge.edge_id, segment[0], segment[1])
                        )
            for first_edge_id, second_edge_id, p1, p2 in contacts:
                score = matcher.score(first, first_edge_id, second, second_edge_id, p1, p2)
                seams.append(score)
                if enforce_rejection and matcher.rejects(score, final=True):
                    return tuple(seams), (
                        f"pattern mismatch between pieces {first.piece_id} and "
                        f"{second.piece_id}: error={score.error:.3f}, "
                        f"confidence={score.confidence:.3f}"
                    )
    return tuple(seams), None


def _piece_has_outer_edge(
    piece: PlacedPiece,
    rectangle: Polygon,
    tolerance: float,
) -> bool:
    boundary = rectangle.boundary
    for edge in piece.edges:
        samples = [
            Point(
                edge.p1.x + (edge.p2.x - edge.p1.x) * fraction,
                edge.p1.y + (edge.p2.y - edge.p1.y) * fraction,
            )
            for fraction in (0.0, 0.25, 0.5, 0.75, 1.0)
        ]
        if max(
            boundary.distance(ShapelyPoint(sample.as_tuple())) for sample in samples
        ) <= tolerance:
            return True
    return False


def check_corner_marker_layout(
    pieces: list[PlacedPiece],
    observations: Mapping[int, PieceObservation],
    rectangle: Polygon,
    config: PatternConfig,
) -> tuple[float, float, str | None]:
    """Check that the two card indices land on opposite rectangle corners.

    Local cut-edge matching cannot distinguish every globally reversed layout.
    A normal playing-card face supplies an independent global constraint: its
    rank/suit indices occupy a pair of diagonal corners.  When fewer than two
    reliable indices are visible this check stays neutral instead of inventing
    evidence.
    """

    markers: list[tuple[float, int, Point, Point | None]] = []
    for placed in pieces:
        observation = observations.get(placed.piece_id)
        if observation is None:
            continue
        for marker in observation.corner_markers:
            world_position = placed.transform.apply(marker.position)
            world_direction: Point | None = None
            if marker.inward_direction is not None:
                direction_tip = placed.transform.apply(
                    Point(
                        marker.position.x + marker.inward_direction.x,
                        marker.position.y + marker.inward_direction.y,
                    )
                )
                world_direction = Point(
                    direction_tip.x - world_position.x,
                    direction_tip.y - world_position.y,
                )
            markers.append(
                (marker.score, placed.piece_id, world_position, world_direction)
            )
    if len(markers) < 2:
        return 0.0, 0.0, None

    corners = [Point(float(x), float(y)) for x, y in list(rectangle.exterior.coords)[:-1]]
    if len(corners) != 4:
        return 0.0, 0.0, None

    assignments = ((0, 2), (2, 0), (1, 3), (3, 1))
    rectangle_centre = Point(
        float(rectangle.centroid.x), float(rectangle.centroid.y)
    )

    pair_candidates = []
    for first, second in itertools.combinations(markers, 2):
        distances = min(
            (
                (
                    math.dist(first[2].as_tuple(), corners[first_corner].as_tuple()),
                    math.dist(second[2].as_tuple(), corners[second_corner].as_tuple()),
                )
                for first_corner, second_corner in assignments
            ),
            key=lambda value: (max(value), sum(value)),
        )
        directional_markers = [
            marker for marker in (first, second) if marker[3] is not None
        ]
        chirality_values: list[float] = []
        for marker in directional_markers:
            direction = marker[3]
            assert direction is not None
            toward_centre = Point(
                rectangle_centre.x - marker[2].x,
                rectangle_centre.y - marker[2].y,
            )
            denominator = max(
                math.hypot(direction.x, direction.y)
                * math.hypot(toward_centre.x, toward_centre.y),
                1e-9,
            )
            chirality_values.append(
                (direction.x * toward_centre.y - direction.y * toward_centre.x)
                / denominator
            )
        mirrored = len(chirality_values) == 2 and any(
            value > -config.corner_chirality_min_abs
            for value in chirality_values
        )
        pair_candidates.append(
            (
                mirrored,
                max(distances),
                sum(distances),
                -min(first[0], second[0]),
                first,
                second,
                chirality_values,
            )
        )

    (
        mirrored,
        maximum_distance,
        _,
        _,
        first,
        second,
        chirality_values,
    ) = min(pair_candidates, key=lambda item: item[:4])
    tolerance = max(config.corner_layout_tolerance_mm, 1e-9)
    layout_score = maximum_distance / tolerance
    confidence = min(
        1.0,
        min(first[0], second[0]) / max(float(config.corner_min_components), 1.0),
    )
    if mirrored:
        return (
            float(layout_score),
            float(confidence),
            "card corner indices are on the mirrored diagonal "
            f"(chirality={max(chirality_values):.3f})",
        )
    if maximum_distance > config.corner_layout_tolerance_mm:
        return (
            float(layout_score),
            float(confidence),
            "card corner indices are not on opposite rectangle corners "
            f"(pieces {first[1]} and {second[1]}, "
            f"distance={maximum_distance:.2f} mm)",
        )
    return float(layout_score), float(confidence), None


def check_pattern_symmetry(
    pieces: list[PlacedPiece],
    observations: Mapping[int, PieceObservation],
    rectangle: Polygon,
    config: PatternConfig,
) -> tuple[float, float, str | None]:
    """Compare card ink with both axis mirrors and a 180-degree rotation."""

    if sum(len(item.corner_markers) for item in observations.values()) < 2:
        return 0.0, 0.0, None
    coordinates = list(rectangle.exterior.coords)[:-1]
    if len(coordinates) != 4:
        return 0.0, 0.0, None
    origin = Point(float(coordinates[0][0]), float(coordinates[0][1]))
    next_corner = Point(float(coordinates[1][0]), float(coordinates[1][1]))
    previous_corner = Point(float(coordinates[-1][0]), float(coordinates[-1][1]))
    axis_x_length = math.dist(origin.as_tuple(), next_corner.as_tuple())
    axis_y_length = math.dist(origin.as_tuple(), previous_corner.as_tuple())
    if axis_x_length <= 1e-8 or axis_y_length <= 1e-8:
        return 0.0, 0.0, None
    axis_x = Point(
        (next_corner.x - origin.x) / axis_x_length,
        (next_corner.y - origin.y) / axis_x_length,
    )
    axis_y = Point(
        (previous_corner.x - origin.x) / axis_y_length,
        (previous_corner.y - origin.y) / axis_y_length,
    )
    pixels_per_mm = config.symmetry_pixels_per_mm
    width = max(2, int(math.ceil(axis_x_length * pixels_per_mm)) + 1)
    height = max(2, int(math.ceil(axis_y_length * pixels_per_mm)) + 1)
    assembled = np.zeros((height, width), dtype=np.uint8)

    def local_pixel(world: Point) -> tuple[float, float]:
        offset_x = world.x - origin.x
        offset_y = world.y - origin.y
        return (
            (offset_x * axis_x.x + offset_y * axis_x.y) * pixels_per_mm,
            (offset_x * axis_y.x + offset_y * axis_y.y) * pixels_per_mm,
        )

    source_basis = np.asarray(((0, 0), (100, 0), (0, 100)), dtype=np.float32)
    for placed in pieces:
        observation = observations.get(placed.piece_id)
        if observation is None or observation.foreground_mask is None:
            continue
        destination = []
        for source_x, source_y in source_basis:
            board = Point(
                (float(source_x) + observation.crop_origin_px[0])
                / observation.pixels_per_mm,
                (float(source_y) + observation.crop_origin_px[1])
                / observation.pixels_per_mm,
            )
            destination.append(local_pixel(placed.transform.apply(board)))
        affine = cv2.getAffineTransform(
            source_basis, np.asarray(destination, dtype=np.float32)
        )
        warped = cv2.warpAffine(
            observation.foreground_mask,
            affine,
            (width, height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
        )
        assembled |= (warped > 0).astype(np.uint8)

    # Rank/suit index components were removed in feature extraction.  Keep all
    # other ink, including a clipped centre pip incorrectly moved to an outer
    # corner, because that is strong evidence against the assembly.
    corner_radius = int(round(config.symmetry_corner_exclusion_mm * pixels_per_mm))
    if corner_radius > 0:
        for centre in (
            (0, 0),
            (width - 1, 0),
            (0, height - 1),
            (width - 1, height - 1),
        ):
            cv2.circle(assembled, centre, corner_radius, 0, thickness=cv2.FILLED)
    foreground_area = float(np.count_nonzero(assembled)) / max(pixels_per_mm**2, 1e-9)
    confidence = min(
        1.0,
        foreground_area / max(config.symmetry_min_foreground_area_mm2, 1e-9),
    )
    if confidence <= 0.0:
        return 0.0, 0.0, None

    radius = max(1, int(round(config.symmetry_match_tolerance_mm * pixels_per_mm)))
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1)
    )

    def mismatch(reference: np.ndarray) -> float:
        dilated_reference = cv2.dilate(reference, kernel)
        dilated_assembled = cv2.dilate(assembled, kernel)
        first_unmatched = np.count_nonzero((assembled > 0) & (dilated_reference == 0))
        second_unmatched = np.count_nonzero(
            (reference > 0) & (dilated_assembled == 0)
        )
        denominator = np.count_nonzero(assembled) + np.count_nonzero(reference)
        return float(first_unmatched + second_unmatched) / max(float(denominator), 1.0)

    errors = (
        mismatch(np.fliplr(assembled)),
        mismatch(np.flipud(assembled)),
        mismatch(np.flipud(np.fliplr(assembled))),
    )
    symmetry_score = max(errors)
    if symmetry_score > config.max_final_symmetry_error:
        return (
            float(symmetry_score),
            float(confidence),
            "card face is not axis/centre symmetric "
            f"(error={symmetry_score:.3f})",
        )
    return float(symmetry_score), float(confidence), None


def check_final_assembly(
    state: SolverState,
    config: SolverConfig,
    matcher: PatternMatcher,
    pattern_config: PatternConfig,
) -> FinalValidation:
    pieces = state.placed_pieces
    source_pieces = [piece.source_piece for piece in pieces]
    strict_strip_pattern = is_uniform_rectangular_strips(source_pieces, config)
    strict_global_pattern = uses_global_pattern_constraints(source_pieces, config)
    sum_area = sum(piece.polygon.area for piece in pieces)
    raw_union = unary_union([piece.polygon for piece in pieces])
    union = raw_union
    if not isinstance(union, Polygon):
        bridge_radius = 0.5 * config.connection_gap_tolerance_mm
        union = raw_union.buffer(bridge_radius, join_style=2).buffer(
            -bridge_radius, join_style=2
        )
    if not isinstance(union, Polygon):
        return FinalValidation(
            False,
            "assembled pieces are not connected within "
            f"{config.connection_gap_tolerance_mm:.2f} mm",
        )
    overlap_area = sum_area - raw_union.area
    for first_index, first in enumerate(pieces):
        valid_overlap, pair_area = check_overlap(
            pieces[first_index + 1 :], first, config, allow_sliver=False
        )
        if not valid_overlap:
            return FinalValidation(
                False, f"final non-sliver overlap area is {pair_area:.3f} mm2"
            )

    rectangle = union.minimum_rotated_rectangle
    if not isinstance(rectangle, Polygon):
        return FinalValidation(False, "minimum rotated rectangle is degenerate")
    short_side, long_side = _rectangle_dimensions(rectangle)
    dimension_tolerance = config.rectangle_dimension_tolerance_mm
    minimum_long_side = (
        config.image_min_long_side_mm
        if matcher.observations
        else config.min_long_side_mm - dimension_tolerance
    )
    if not (
        config.min_short_side_mm - dimension_tolerance
        <= short_side
        <= config.max_short_side_mm + dimension_tolerance
        and minimum_long_side
        <= long_side
        <= config.max_long_side_mm + dimension_tolerance
    ):
        return FinalValidation(
            False,
            f"rectangle dimensions {long_side:.2f} x {short_side:.2f} mm are outside limits",
        )

    gap_area = max(0.0, float(rectangle.area - raw_union.area))
    gap_ratio = gap_area / max(float(rectangle.area), 1e-9)
    if gap_area > config.max_final_gap_area_mm2 or gap_ratio > config.max_final_gap_ratio:
        return FinalValidation(
            False,
            f"rectangle gap is {gap_area:.2f} mm2 ({gap_ratio:.2%})",
        )
    # Area alone cannot distinguish a shallow raster gap from a narrow but
    # deep missing corner.  Require every point of the fitted rectangle frame
    # to lie close to actual piece material.  This is deliberately one-way:
    # following the union exterior back into an allowed internal seam would
    # incorrectly reject otherwise complete cards assembled with small gaps.
    boundary_support = raw_union.buffer(
        config.max_rectangle_boundary_gap_mm,
        join_style=2,
    )
    if not boundary_support.covers(rectangle.boundary):
        uncovered = rectangle.boundary.difference(boundary_support)
        return FinalValidation(
            False,
            "rectangle boundary has an unsupported segment "
            f"({uncovered.length:.2f} mm outside the "
            f"{config.max_rectangle_boundary_gap_mm:.2f} mm tolerance)",
        )
    if union.interiors:
        hole_area = sum(Polygon(interior).area for interior in union.interiors)
        if hole_area > config.max_final_gap_area_mm2:
            return FinalValidation(False, f"internal hole area is {hole_area:.2f} mm2")
    for piece in pieces:
        if not _piece_has_outer_edge(piece, rectangle, config.outer_edge_tolerance_mm):
            return FinalValidation(False, f"piece {piece.piece_id} has no rectangle outer edge")

    seams, pattern_error = discover_and_score_seams(
        pieces,
        matcher,
        config,
        pattern_config,
        enforce_rejection=not strict_strip_pattern,
    )
    if pattern_error is not None:
        return FinalValidation(False, pattern_error, seams=seams)
    informative_weight = sum(
        seam.confidence * math.dist(seam.p1.as_tuple(), seam.p2.as_tuple())
        for seam in seams
    )
    total_length = sum(math.dist(seam.p1.as_tuple(), seam.p2.as_tuple()) for seam in seams)
    if informative_weight > 1e-9:
        pattern_score = sum(
            seam.error
            * seam.confidence
            * math.dist(seam.p1.as_tuple(), seam.p2.as_tuple())
            for seam in seams
        ) / informative_weight
    else:
        pattern_score = 0.0
    pattern_confidence = informative_weight / max(total_length, 1e-9)
    corner_layout_score, corner_layout_confidence, corner_error = (
        check_corner_marker_layout(
            pieces,
            matcher.observations,
            rectangle,
            pattern_config,
        )
    )
    if strict_global_pattern and corner_error is not None:
        return FinalValidation(
            False,
            corner_error,
            corner_layout_score=corner_layout_score,
            corner_layout_confidence=corner_layout_confidence,
            seams=seams,
        )
    symmetry_score, symmetry_confidence, symmetry_error = check_pattern_symmetry(
        pieces,
        matcher.observations,
        rectangle,
        pattern_config,
    )
    if strict_strip_pattern and symmetry_error is not None:
        return FinalValidation(
            False,
            symmetry_error,
            rectangle=rectangle,
            long_side_mm=long_side,
            short_side_mm=short_side,
            geometry_score=gap_ratio,
            pattern_score=float(pattern_score),
            pattern_confidence=float(min(1.0, pattern_confidence)),
            corner_layout_score=corner_layout_score,
            corner_layout_confidence=corner_layout_confidence,
            symmetry_score=symmetry_score,
            symmetry_confidence=symmetry_confidence,
            strict_global_pattern=True,
            seams=seams,
        )
    # Symmetry is useful ranking evidence, but not a universal playing-card
    # invariant: a single large ace pip and many face-card illustrations are
    # intentionally asymmetric under a 180-degree rotation.  Seam continuity
    # and corner-index chirality remain hard checks; symmetry stays a cost.
    if not strict_global_pattern:
        # Irregular cuts normally have a unique geometric assembly.  Retain
        # the diagnostic scores, but do not let noisy rank-component grouping
        # outweigh the cut shape or reject an otherwise exact rigid solution.
        corner_layout_confidence = 0.0
        symmetry_confidence = 0.0
    return FinalValidation(
        True,
        rectangle=rectangle,
        long_side_mm=long_side,
        short_side_mm=short_side,
        geometry_score=gap_ratio,
        pattern_score=float(pattern_score),
        pattern_confidence=float(min(1.0, pattern_confidence)),
        corner_layout_score=corner_layout_score,
        corner_layout_confidence=corner_layout_confidence,
        symmetry_score=symmetry_score,
        symmetry_confidence=symmetry_confidence,
        strict_global_pattern=strict_global_pattern,
        seams=seams,
    )
