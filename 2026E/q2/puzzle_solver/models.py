"""Domain models for pieces, placed pieces and DFS state."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Iterable, Sequence

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
    """An original, directed piece edge."""

    piece_id: int
    edge_id: int
    p1: Point
    p2: Point
    length: float = field(init=False)
    angle: float = field(init=False)

    def __post_init__(self) -> None:
        edge_length = distance(self.p1, self.p2)
        if edge_length <= 1e-9:
            raise ValueError(f"piece {self.piece_id} has a zero-length edge")
        object.__setattr__(self, "length", edge_length)
        object.__setattr__(self, "angle", edge_angle(self.p1, self.p2))


@dataclass(frozen=True)
class Piece:
    """An immutable input fragment whose coordinates are in millimetres."""

    id: int
    vertices: tuple[Point, ...] | Sequence[Point | Sequence[float]]
    edges: tuple[Edge, ...] = field(init=False)
    polygon: Polygon = field(init=False, repr=False, compare=False)
    area: float = field(init=False)
    centroid: Point = field(init=False)
    bounds: tuple[float, float, float, float] = field(init=False)

    def __post_init__(self) -> None:
        vertices = tuple(as_point(vertex) for vertex in self.vertices)
        if len(vertices) < 3 or len(vertices) > 5:
            raise ValueError("a piece must have between 3 and 5 vertices")
        if any(
            not math.isfinite(coordinate)
            for vertex in vertices
            for coordinate in vertex.as_tuple()
        ):
            raise ValueError(f"piece {self.id} contains a non-finite coordinate")
        polygon = polygon_from_points(vertices)
        if not polygon.is_valid:
            raise ValueError(f"piece {self.id} is not a valid simple polygon")
        if polygon.area <= 1e-9:
            raise ValueError(f"piece {self.id} has zero area")

        edges = tuple(
            Edge(self.id, index, vertex, vertices[(index + 1) % len(vertices)])
            for index, vertex in enumerate(vertices)
        )
        object.__setattr__(self, "vertices", vertices)
        object.__setattr__(self, "edges", edges)
        object.__setattr__(self, "polygon", polygon)
        object.__setattr__(self, "area", float(polygon.area))
        object.__setattr__(
            self,
            "centroid",
            Point(float(polygon.centroid.x), float(polygon.centroid.y)),
        )
        object.__setattr__(self, "bounds", tuple(float(value) for value in polygon.bounds))

    @property
    def longest_edge_length(self) -> float:
        return max(edge.length for edge in self.edges)


@dataclass(frozen=True, slots=True)
class OpenEdge:
    """A transformed boundary edge not yet paired with another piece."""

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
    """A piece and its solved rigid pose."""

    piece_id: int
    rotation: float
    translation: tuple[float, float]
    polygon: Polygon = field(repr=False, compare=False)
    vertices: tuple[Point, ...]
    source_piece: Piece = field(repr=False, compare=False)

    @classmethod
    def from_piece(cls, piece: Piece, transform: RigidTransform) -> "PlacedPiece":
        vertices = transform_points(piece.vertices, transform)
        return cls(
            piece_id=piece.id,
            rotation=transform.rotation_rad,
            translation=transform.translation,
            polygon=Polygon([point.as_tuple() for point in vertices]),
            vertices=vertices,
            source_piece=piece,
        )

    @property
    def rotation_deg(self) -> float:
        return math.degrees(self.rotation)

    @property
    def x(self) -> float:
        return self.translation[0]

    @property
    def y(self) -> float:
        return self.translation[1]

    @property
    def centroid(self) -> Point:
        return Point(float(self.polygon.centroid.x), float(self.polygon.centroid.y))

    def edge(self, edge_id: int) -> OpenEdge:
        next_index = (edge_id + 1) % len(self.vertices)
        return OpenEdge(
            self.piece_id,
            edge_id,
            self.vertices[edge_id],
            self.vertices[next_index],
        )

    @property
    def edges(self) -> tuple[OpenEdge, ...]:
        return tuple(self.edge(index) for index in range(len(self.vertices)))


@dataclass(frozen=True, slots=True)
class Connection:
    """A pair of edges explicitly joined by the DFS."""

    first_piece_id: int
    first_edge_id: int
    second_piece_id: int
    second_edge_id: int
    p1: Point
    p2: Point


@dataclass
class SolverState:
    """One immutable-by-convention DFS branch."""

    placed_pieces: list[PlacedPiece]
    used_piece_ids: set[int]
    open_edges: list[OpenEdge]
    connections: list[Connection] = field(default_factory=list)

    def copy(self) -> "SolverState":
        """Copy mutable containers while sharing immutable geometry objects."""

        return SolverState(
            placed_pieces=list(self.placed_pieces),
            used_piece_ids=set(self.used_piece_ids),
            open_edges=list(self.open_edges),
            connections=list(self.connections),
        )

    def placed_by_id(self, piece_id: int) -> PlacedPiece:
        for placed in self.placed_pieces:
            if placed.piece_id == piece_id:
                return placed
        raise KeyError(piece_id)


@dataclass(frozen=True)
class Solution:
    """Public solve result."""

    success: bool
    placed_pieces: tuple[PlacedPiece, ...] = ()
    rectangle_width_mm: float | None = None
    rectangle_height_mm: float | None = None
    score: float | None = None
    rectangle: Polygon | None = field(default=None, repr=False, compare=False)
    connections: tuple[Connection, ...] = ()
    official_dimensions_valid: bool | None = None
    best_effort: bool = False
    validation_warning: str | None = None
    reason: str | None = None

    @property
    def poses(self) -> tuple[dict[str, float | int], ...]:
        """Return compact serialisable pose dictionaries."""

        return tuple(
            {
                "piece_id": placed.piece_id,
                "x": placed.x,
                "y": placed.y,
                "rotation_deg": placed.rotation_deg,
            }
            for placed in self.placed_pieces
        )


def make_pieces(items: Iterable[tuple[int, Sequence[Sequence[float]]]]) -> list[Piece]:
    """Convenience helper for constructing pieces from numeric pairs."""

    return [Piece(piece_id, vertices) for piece_id, vertices in items]
