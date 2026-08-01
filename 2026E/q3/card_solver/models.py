"""Domain models shared by image input and search."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Sequence

import numpy as np
from shapely.geometry import Polygon

from .geometry import (
    Point,
    RigidTransform,
    as_point,
    distance,
    edge_angle,
    polygon_from_points,
    transform_points,
)


@dataclass(frozen=True, slots=True)
class Edge:
    piece_id: int
    edge_id: int
    p1: Point
    p2: Point
    length: float = field(init=False)
    angle: float = field(init=False)

    def __post_init__(self) -> None:
        length = distance(self.p1, self.p2)
        if length <= 1e-8:
            raise ValueError(f"piece {self.piece_id} has a zero-length edge")
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "angle", edge_angle(self.p1, self.p2))


@dataclass(frozen=True)
class Piece:
    """One immutable polygon in calibrated source-board coordinates."""

    id: int
    vertices: tuple[Point, ...] | Sequence[Point | Sequence[float]]
    edges: tuple[Edge, ...] = field(init=False)
    polygon: Polygon = field(init=False, repr=False, compare=False)
    area: float = field(init=False)
    centroid: Point = field(init=False)
    bounds: tuple[float, float, float, float] = field(init=False)

    def __post_init__(self) -> None:
        vertices = tuple(as_point(vertex) for vertex in self.vertices)
        if not 3 <= len(vertices) <= 5:
            raise ValueError("a piece must have between three and five vertices")
        if any(
            not math.isfinite(coordinate)
            for point in vertices
            for coordinate in point.as_tuple()
        ):
            raise ValueError("piece coordinates must be finite")
        polygon = polygon_from_points(vertices)
        if not polygon.is_valid or polygon.area <= 1e-7:
            raise ValueError(f"piece {self.id} is not a valid simple polygon")
        edges = tuple(
            Edge(self.id, index, vertex, vertices[(index + 1) % len(vertices)])
            for index, vertex in enumerate(vertices)
        )
        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "polygon", polygon)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "area", float(polygon.area))
        object.__setattr__(
            self,
            "centroid",
            Point(float(polygon.centroid.x), float(polygon.centroid.y)),
        )
        object.__setattr__(self, "bounds", tuple(float(v) for v in polygon.bounds))

    @property
    def longest_edge_length(self) -> float:
        return max(edge.length for edge in self.edges)


@dataclass(frozen=True, slots=True)
class OpenEdge:
    piece_id: int
    edge_id: int
    p1: Point
    p2: Point
    length: float = field(init=False)
    angle: float = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "length", distance(self.p1, self.p2))
        object.__setattr__(self, "angle", edge_angle(self.p1, self.p2))


@dataclass(frozen=True)
class PlacedPiece:
    piece_id: int
    transform: RigidTransform
    polygon: Polygon = field(repr=False, compare=False)
    vertices: tuple[Point, ...]
    source_piece: Piece = field(repr=False, compare=False)

    @classmethod
    def from_piece(cls, piece: Piece, transform: RigidTransform) -> "PlacedPiece":
        vertices = transform_points(piece.vertices, transform)
        return cls(
            piece.id,
            transform,
            Polygon([point.as_tuple() for point in vertices]),
            vertices,
            piece,
        )

    @property
    def rotation(self) -> float:
        return self.transform.rotation_rad

    @property
    def rotation_deg(self) -> float:
        return math.degrees(self.rotation)

    @property
    def x(self) -> float:
        return self.transform.translation[0]

    @property
    def y(self) -> float:
        return self.transform.translation[1]

    @property
    def centroid(self) -> Point:
        return Point(float(self.polygon.centroid.x), float(self.polygon.centroid.y))

    def edge(self, edge_id: int) -> OpenEdge:
        return OpenEdge(
            self.piece_id,
            edge_id,
            self.vertices[edge_id],
            self.vertices[(edge_id + 1) % len(self.vertices)],
        )

    @property
    def edges(self) -> tuple[OpenEdge, ...]:
        return tuple(self.edge(index) for index in range(len(self.vertices)))


@dataclass(frozen=True)
class EdgeFeature:
    """Canonical samples from one edge, directed from its p1 to p2."""

    edge_id: int
    positions_mm: np.ndarray = field(repr=False, compare=False)
    lab: np.ndarray = field(repr=False, compare=False)
    classes: np.ndarray = field(repr=False, compare=False)
    line_profile: np.ndarray = field(repr=False, compare=False)
    information: np.ndarray = field(repr=False, compare=False)
    valid: np.ndarray = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class CornerMarker:
    """One detected rank/suit index in source-board millimetres."""

    position: Point
    score: float
    component_count: int
    inward_direction: Point | None = None


@dataclass
class PieceObservation:
    """Geometry plus the undistorted source texture belonging to one piece."""

    piece: Piece
    texture_bgr: np.ndarray = field(repr=False)
    mask: np.ndarray = field(repr=False)
    crop_origin_px: tuple[int, int]
    pixels_per_mm: float
    edge_features: dict[int, EdgeFeature] = field(default_factory=dict, repr=False)
    corner_marker_scores: tuple[float, ...] = field(default_factory=tuple)
    corner_markers: tuple[CornerMarker, ...] = field(default_factory=tuple)
    foreground_mask: np.ndarray | None = field(default=None, repr=False)
    red_ink_area_mm2: float = 0.0
    black_ink_area_mm2: float = 0.0

    def mm_to_crop_pixel(self, point: Point) -> tuple[float, float]:
        return (
            point.x * self.pixels_per_mm - self.crop_origin_px[0],
            point.y * self.pixels_per_mm - self.crop_origin_px[1],
        )


@dataclass(frozen=True, slots=True)
class SeamScore:
    first_piece_id: int
    first_edge_id: int
    second_piece_id: int
    second_edge_id: int
    p1: Point
    p2: Point
    error: float
    confidence: float

    @property
    def informative(self) -> bool:
        return self.confidence > 0.0


@dataclass
class SolverState:
    placed_pieces: list[PlacedPiece]
    used_piece_ids: set[int]
    open_edges: list[OpenEdge]
    seams: list[SeamScore] = field(default_factory=list)

    def copy(self) -> "SolverState":
        return SolverState(
            list(self.placed_pieces),
            set(self.used_piece_ids),
            list(self.open_edges),
            list(self.seams),
        )

    def placed_by_id(self, piece_id: int) -> PlacedPiece:
        return next(piece for piece in self.placed_pieces if piece.piece_id == piece_id)


@dataclass(frozen=True)
class Solution:
    success: bool
    placed_pieces: tuple[PlacedPiece, ...] = ()
    rectangle_width_mm: float | None = None
    rectangle_height_mm: float | None = None
    geometry_score: float | None = None
    pattern_score: float | None = None
    pattern_confidence: float | None = None
    corner_layout_score: float | None = None
    corner_layout_confidence: float | None = None
    symmetry_score: float | None = None
    symmetry_confidence: float | None = None
    rectangle: Polygon | None = field(default=None, repr=False, compare=False)
    seams: tuple[SeamScore, ...] = ()
    ignored_piece_ids: tuple[int, ...] = ()
    reason: str | None = None
    best_effort: bool = False
    validation_warning: str | None = None

    @property
    def poses(self) -> tuple[dict[str, float | int], ...]:
        return tuple(
            {
                "piece_id": item.piece_id,
                "x": item.x,
                "y": item.y,
                "rotation_deg": item.rotation_deg,
            }
            for item in self.placed_pieces
        )


@dataclass(frozen=True)
class CardPuzzleInput:
    observations: tuple[PieceObservation, ...]
    rectified_bgr: np.ndarray = field(repr=False, compare=False)
    paper_size_mm: tuple[float, float]
    pixels_per_mm: float
    layout: str
    divider_mm: float
    image_path: str | None = None
    detected_candidate_count: int = 0
    discarded_candidate_ids: tuple[int, ...] = ()

    @property
    def pieces(self) -> tuple[Piece, ...]:
        return tuple(observation.piece for observation in self.observations)
