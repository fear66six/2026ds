"""Deterministic artificial puzzle sets used by the demo and tests."""

import math

from .geometry import RigidTransform
from .models import Piece


def simple_four_piece_rectangle() -> list[Piece]:
    """Four quadrilaterals forming a 100 by 70 mm rectangle."""

    return [
        Piece(0, [(0, 0), (45, 0), (45, 30), (0, 30)]),
        Piece(1, [(45, 0), (100, 0), (100, 30), (45, 30)]),
        Piece(2, [(0, 30), (45, 30), (45, 70), (0, 70)]),
        Piece(3, [(45, 30), (100, 30), (100, 70), (45, 70)]),
    ]


def irregular_three_piece_rectangle() -> list[Piece]:
    """A triangle and two quadrilaterals forming 110 by 60 mm."""

    return [
        Piece(0, [(0, 0), (110, 0), (55, 30)]),
        Piece(1, [(0, 0), (55, 30), (55, 60), (0, 60)]),
        Piece(2, [(55, 30), (110, 0), (110, 60), (55, 60)]),
    ]


def backtracking_rectangle() -> list[Piece]:
    """Identical pieces with several plausible matches and a dead branch."""

    return [Piece(index, [(0, 0), (50, 0), (50, 35), (0, 35)]) for index in range(4)]


def overlapping_candidate_puzzle() -> list[Piece]:
    """An impossible set where a second notch filler would overlap the first."""

    filler = [(0, 70), (50, 35), (100, 70)]
    return [
        Piece(0, [(0, 0), (100, 0), (100, 70), (50, 35), (0, 70)]),
        Piece(1, filler),
        Piece(2, filler),
    ]


def reversed_endpoint_rectangle() -> list[Piece]:
    """Two halves for which the direct mapping fails and reversed succeeds."""

    return [
        Piece(0, [(0, 0), (50, 0), (50, 60), (0, 60)]),
        Piece(1, [(50, 0), (100, 0), (100, 60), (50, 60)]),
    ]


def out_of_range_rectangle() -> list[Piece]:
    """Two valid squares whose 80 by 40 rectangle is too small."""

    return [
        Piece(0, [(0, 0), (40, 0), (40, 40), (0, 40)]),
        Piece(1, [(40, 0), (80, 0), (80, 40), (40, 40)]),
    ]


def scattered_rotated_four_piece_rectangle() -> list[Piece]:
    """The first sample after independent arbitrary rigid transforms."""

    rotations_deg = (23.0, -71.0, 112.0, -17.0)
    translations = ((210.0, 40.0), (-50.0, 130.0), (300.0, -80.0), (75.0, 190.0))
    scattered: list[Piece] = []
    for source, angle_deg, translation in zip(
        simple_four_piece_rectangle(), rotations_deg, translations
    ):
        transform = RigidTransform(math.radians(angle_deg), translation)
        scattered.append(
            Piece(source.id, [transform.apply(vertex) for vertex in source.vertices])
        )
    return scattered


def board_scattered_four_piece_rectangle() -> list[Piece]:
    """Four irregular pieces scattered above an A4 board divider.

    The supplied coordinates are already in board millimetres.  Every piece
    is independently rotated and translated, while its source geometry tiles
    an exact 100 by 70 mm rectangle.
    """

    tiled_vertices = (
        ((0, 0), (55, 0), (50, 35), (0, 28)),
        ((55, 0), (100, 0), (100, 42), (50, 35)),
        ((0, 28), (50, 35), (45, 70), (0, 70)),
        ((50, 35), (100, 42), (100, 70), (45, 70)),
    )
    centers = ((48.0, 35.0), (157.0, 35.0), (48.0, 105.0), (155.0, 100.0))
    rotations_deg = (7.0, -25.0, 28.0, 12.0)

    scattered: list[Piece] = []
    for piece_id, (vertices, center, angle_deg) in enumerate(
        zip(tiled_vertices, centers, rotations_deg)
    ):
        source = Piece(piece_id, vertices)
        angle_rad = math.radians(angle_deg)
        cos_angle = math.cos(angle_rad)
        sin_angle = math.sin(angle_rad)
        rotated_centroid = (
            cos_angle * source.centroid.x - sin_angle * source.centroid.y,
            sin_angle * source.centroid.x + cos_angle * source.centroid.y,
        )
        transform = RigidTransform(
            angle_rad,
            (
                center[0] - rotated_centroid[0],
                center[1] - rotated_centroid[1],
            ),
        )
        scattered.append(
            Piece(source.id, [transform.apply(vertex) for vertex in source.vertices])
        )
    return scattered


def partial_edge_three_piece_rectangle() -> list[Piece]:
    """A 120 by 70 mm tiling with one 120 mm edge split into 50 + 70 mm."""

    return [
        Piece(0, [(0, 0), (120, 0), (120, 35), (0, 35)]),
        Piece(1, [(0, 35), (50, 35), (50, 70), (0, 70)]),
        Piece(2, [(50, 35), (120, 35), (120, 70), (50, 70)]),
    ]
