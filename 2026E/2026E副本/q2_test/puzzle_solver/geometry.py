"""Small, unit-aware geometry primitives used by the solver."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
from shapely.geometry import LineString, Polygon


@dataclass(frozen=True, slots=True)
class Point:
    """A two-dimensional point in millimetres."""

    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (float(self.x), float(self.y))

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield self.x
        yield self.y


@dataclass(frozen=True, slots=True)
class RigidTransform:
    """A rotation about the origin followed by a translation."""

    rotation_rad: float = 0.0
    translation: tuple[float, float] = (0.0, 0.0)

    @property
    def rotation_deg(self) -> float:
        return math.degrees(self.rotation_rad)

    def apply(self, point: Point) -> Point:
        cos_angle = math.cos(self.rotation_rad)
        sin_angle = math.sin(self.rotation_rad)
        x = cos_angle * point.x - sin_angle * point.y + self.translation[0]
        y = sin_angle * point.x + cos_angle * point.y + self.translation[1]
        return Point(x, y)


def as_point(value: Point | Sequence[float]) -> Point:
    """Convert a point-like pair to :class:`Point`."""

    if isinstance(value, Point):
        return value
    if len(value) != 2:
        raise ValueError("a point must contain exactly two coordinates")
    return Point(float(value[0]), float(value[1]))


def distance(first: Point, second: Point) -> float:
    """Return Euclidean distance in millimetres."""

    return math.hypot(second.x - first.x, second.y - first.y)


def edge_angle(first: Point, second: Point) -> float:
    """Return the directed edge angle in radians."""

    return math.atan2(second.y - first.y, second.x - first.x)


def normalize_angle(angle_rad: float) -> float:
    """Normalize an angle to ``[-pi, pi]``."""

    normalized = (angle_rad + math.pi) % (2.0 * math.pi) - math.pi
    return math.pi if math.isclose(normalized, -math.pi) else normalized


def cross(edge_start: Point, edge_end: Point, point: Point) -> float:
    """Return the 2-D cross product ``edge x (point - edge_start)``."""

    return ((edge_end.x - edge_start.x) * (point.y - edge_start.y)) - (
        (edge_end.y - edge_start.y) * (point.x - edge_start.x)
    )


def transform_points(
    points: Iterable[Point], transform: RigidTransform
) -> tuple[Point, ...]:
    """Apply one rigid transform to a sequence of points."""

    return tuple(transform.apply(point) for point in points)


def polygon_from_points(points: Sequence[Point]) -> Polygon:
    """Build a Shapely polygon without changing the input vertex order."""

    return Polygon([point.as_tuple() for point in points])


def transform_polygon(points: Sequence[Point], transform: RigidTransform) -> Polygon:
    """Create the transformed polygon using rotation and translation only."""

    return polygon_from_points(transform_points(points, transform))


def line_from_points(first: Point, second: Point) -> LineString:
    """Create a Shapely line segment."""

    return LineString([first.as_tuple(), second.as_tuple()])


def polygon_corner_angles_deg(polygon: Polygon) -> list[float]:
    """Return the smaller angle at each exterior vertex in degrees."""

    coordinates = list(polygon.exterior.coords)[:-1]
    angles: list[float] = []
    for index, current in enumerate(coordinates):
        previous = coordinates[index - 1]
        following = coordinates[(index + 1) % len(coordinates)]
        vector_a = np.asarray(previous, dtype=float) - np.asarray(current, dtype=float)
        vector_b = np.asarray(following, dtype=float) - np.asarray(current, dtype=float)
        denominator = float(np.linalg.norm(vector_a) * np.linalg.norm(vector_b))
        if denominator <= 1e-12:
            angles.append(0.0)
            continue
        cosine = float(np.clip(np.dot(vector_a, vector_b) / denominator, -1.0, 1.0))
        angles.append(math.degrees(math.acos(cosine)))
    return angles


def rectangle_dimensions(polygon: Polygon) -> tuple[float, float, Polygon]:
    """Return short side, long side and minimum rotated rectangle."""

    rectangle = polygon.minimum_rotated_rectangle
    coordinates = list(rectangle.exterior.coords)[:-1]
    if len(coordinates) != 4:
        return (0.0, 0.0, rectangle)
    lengths = [
        math.dist(coordinates[index], coordinates[(index + 1) % 4])
        for index in range(4)
    ]
    return (min(lengths), max(lengths), rectangle)

