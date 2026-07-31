"""Small, dependency-light geometry helpers for rigid polygon assembly."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
from shapely.geometry import Polygon


@dataclass(frozen=True, slots=True)
class Point:
    """A two-dimensional point measured in millimetres."""

    x: float
    y: float

    def as_tuple(self) -> tuple[float, float]:
        return (self.x, self.y)

    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Point") -> "Point":
        return Point(self.x - other.x, self.y - other.y)

    def scaled(self, factor: float) -> "Point":
        return Point(self.x * factor, self.y * factor)


def as_point(value: Point | Sequence[float]) -> Point:
    if isinstance(value, Point):
        return value
    if len(value) != 2:
        raise ValueError("a point requires exactly two coordinates")
    return Point(float(value[0]), float(value[1]))


def distance(first: Point, second: Point) -> float:
    return math.hypot(second.x - first.x, second.y - first.y)


def cross(vector: Point, offset: Point) -> float:
    return vector.x * offset.y - vector.y * offset.x


def edge_angle(first: Point, second: Point) -> float:
    return math.atan2(second.y - first.y, second.x - first.x)


def normalize_angle(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


@dataclass(frozen=True, slots=True)
class RigidTransform:
    """Rotation and translation only; scale and reflection are impossible."""

    rotation_rad: float = 0.0
    translation: tuple[float, float] = (0.0, 0.0)

    def apply(self, point: Point) -> Point:
        cosine = math.cos(self.rotation_rad)
        sine = math.sin(self.rotation_rad)
        return Point(
            cosine * point.x - sine * point.y + self.translation[0],
            sine * point.x + cosine * point.y + self.translation[1],
        )

    def inverse_apply(self, point: Point) -> Point:
        x = point.x - self.translation[0]
        y = point.y - self.translation[1]
        cosine = math.cos(self.rotation_rad)
        sine = math.sin(self.rotation_rad)
        return Point(cosine * x + sine * y, -sine * x + cosine * y)

    def compose(self, inner: "RigidTransform") -> "RigidTransform":
        """Return the transform equivalent to ``self(inner(point))``."""

        translated_origin = self.apply(Point(*inner.translation))
        return RigidTransform(
            normalize_angle(self.rotation_rad + inner.rotation_rad),
            translated_origin.as_tuple(),
        )


def transform_points(
    points: Iterable[Point], transform: RigidTransform
) -> tuple[Point, ...]:
    return tuple(transform.apply(point) for point in points)


def polygon_from_points(points: Sequence[Point]) -> Polygon:
    polygon = Polygon([point.as_tuple() for point in points])
    if not polygon.is_valid:
        repaired = polygon.buffer(0)
        if not isinstance(repaired, Polygon):
            return polygon
        polygon = repaired
    return polygon


def signed_area(points: Sequence[Point]) -> float:
    return 0.5 * sum(
        first.x * second.y - second.x * first.y
        for first, second in zip(points, points[1:] + points[:1])
    )


def polygon_angles_deg(polygon: Polygon) -> tuple[float, ...]:
    coordinates = list(polygon.exterior.coords)[:-1]
    output: list[float] = []
    for index, current in enumerate(coordinates):
        previous = np.asarray(coordinates[index - 1], dtype=float) - current
        following = (
            np.asarray(coordinates[(index + 1) % len(coordinates)], dtype=float)
            - current
        )
        denominator = float(np.linalg.norm(previous) * np.linalg.norm(following))
        if denominator <= 1e-12:
            continue
        cosine = float(np.clip(np.dot(previous, following) / denominator, -1.0, 1.0))
        output.append(math.degrees(math.acos(cosine)))
    return tuple(output)


def interpolate_transform(
    start: RigidTransform,
    end: RigidTransform,
    fraction: float,
) -> RigidTransform:
    fraction = min(1.0, max(0.0, fraction))
    angle_delta = normalize_angle(end.rotation_rad - start.rotation_rad)
    return RigidTransform(
        normalize_angle(start.rotation_rad + angle_delta * fraction),
        (
            start.translation[0]
            + (end.translation[0] - start.translation[0]) * fraction,
            start.translation[1]
            + (end.translation[1] - start.translation[1]) * fraction,
        ),
    )
