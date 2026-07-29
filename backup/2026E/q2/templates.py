"""图2 四片模板（test.png / --fig2-fallback 专用）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

Point = Tuple[float, float]

DIAG_TOP = (2.0, 0.0)
DIAG_POINT_A = (3.6, 1.2)
DIAG_POINT_B = (7.6, 4.2)


@dataclass
class PieceTemplate:
    name: str
    local_vertices: List[Point]

    @property
    def area(self) -> float:
        pts = self.local_vertices
        n = len(pts)
        return float(
            abs(sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))) / 2.0
        )

    def world_vertices(self, origin: Point, angle_deg: float = 0.0) -> np.ndarray:
        ox, oy = origin
        rad = np.deg2rad(angle_deg)
        c, s = np.cos(rad), np.sin(rad)
        return np.array(
            [[x * c - y * s + ox, x * s + y * c + oy] for x, y in self.local_vertices],
            dtype=np.float64,
        )


PIECE_TEMPLATES: List[PieceTemplate] = [
    PieceTemplate("P1", [(0.0, 0.0), (2.0, 0.0), DIAG_POINT_A, (0.0, 2.0)]),
    PieceTemplate("P2", [(0.0, 2.0), DIAG_POINT_A, DIAG_POINT_B, (0.0, 3.0)]),
    PieceTemplate("P3", [(0.0, 3.0), DIAG_POINT_B, (10.0, 6.0), (0.0, 6.0)]),
    PieceTemplate("P4", [DIAG_TOP, (10.0, 0.0), (10.0, 6.0)]),
]


def get_template(name: str) -> PieceTemplate:
    for tpl in PIECE_TEMPLATES:
        if tpl.name == name:
            return tpl
    raise KeyError(name)
