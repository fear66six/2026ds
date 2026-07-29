"""自备 4 片碎片的模板定义（单位 cm，局部坐标系）"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np

Point = Tuple[float, float]

# 图 2 目标矩形总尺寸
TARGET_RECT_WIDTH_CM = 10.0
TARGET_RECT_HEIGHT_CM = 6.0

# 主对角线 (2,6)→(10,0) 上的分割点（图 2 标注 2cm / 3cm 处）
DIAG_TOP = (2.0, 0.0)       # 图坐标 (2,6) → 代码 y 向下
DIAG_POINT_A = (3.6, 1.2)   # 距顶点 2cm
DIAG_POINT_B = (7.6, 4.2)   # 距右下角 3cm


@dataclass
class PieceTemplate:
    name: str
    local_vertices: List[Point]
    color_hint: str = ""

    @property
    def area(self) -> float:
        return float(abs(_polygon_area(self.local_vertices)))

    @property
    def bbox(self) -> Tuple[float, float, float, float]:
        xs = [p[0] for p in self.local_vertices]
        ys = [p[1] for p in self.local_vertices]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return min_x, min_y, max_x - min_x, max_y - min_y

    def world_vertices(self, origin: Point, angle_deg: float = 0.0) -> np.ndarray:
        """将局部顶点变换到世界坐标（cm）"""
        ox, oy = origin
        rad = np.deg2rad(angle_deg)
        c, s = np.cos(rad), np.sin(rad)
        pts = []
        for x, y in self.local_vertices:
            rx = x * c - y * s + ox
            ry = x * s + y * c + oy
            pts.append((rx, ry))
        return np.array(pts, dtype=np.float64)

    def vertices_at(self, top_left: Point) -> List[Point]:
        """将碎片平移到指定左上角附近（按 bbox 对齐）"""
        min_x, min_y, _, _ = self.bbox
        dx = top_left[0] - min_x
        dy = top_left[1] - min_y
        return [(x + dx, y + dy) for x, y in self.local_vertices]


def _polygon_area(vertices: List[Point]) -> float:
    n = len(vertices)
    area = 0.0
    for i in range(n):
        x1, y1 = vertices[i]
        x2, y2 = vertices[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


# 图 2：四片碎片拼成 10cm × 6cm 目标矩形
# 坐标系：目标矩形左上角为 (0,0)，x 向右，y 向下（与 A4 图像坐标一致）
# 图 2 原始坐标（左下角为原点、y 向上）换算：y_code = 6 - y_figure
PIECE_TEMPLATES: List[PieceTemplate] = [
    PieceTemplate(
        name="P1_左上四边形",
        local_vertices=[
            (0.0, 0.0),
            (2.0, 0.0),
            DIAG_POINT_A,
            (0.0, 2.0),
        ],
        color_hint="左上块，左边 2+1+3cm",
    ),
    PieceTemplate(
        name="P2_左中四边形",
        local_vertices=[
            (0.0, 2.0),
            DIAG_POINT_A,
            DIAG_POINT_B,
            (0.0, 3.0),
        ],
        color_hint="左中块，对角线分割",
    ),
    PieceTemplate(
        name="P3_左下四边形",
        local_vertices=[
            (0.0, 3.0),
            DIAG_POINT_B,
            (10.0, 6.0),
            (0.0, 6.0),
        ],
        color_hint="左下块，含底边",
    ),
    PieceTemplate(
        name="P4_右三角形",
        local_vertices=[
            DIAG_TOP,
            (10.0, 0.0),
            (10.0, 6.0),
        ],
        color_hint="右侧大三角形 8×6cm",
    ),
]

TARGET_ASSEMBLY: List[Tuple[str, Point, float]] = [
    (tpl.name, (0.0, 0.0), 0.0) for tpl in PIECE_TEMPLATES
]


def get_template(name: str) -> PieceTemplate:
    for tpl in PIECE_TEMPLATES:
        if tpl.name == name:
            return tpl
    raise KeyError(name)


def verify_templates() -> dict:
    """校验四片面积之和是否等于 10×6"""
    total = sum(t.area for t in PIECE_TEMPLATES)
    expected = TARGET_RECT_WIDTH_CM * TARGET_RECT_HEIGHT_CM
    return {
        "piece_areas": {t.name: round(t.area, 2) for t in PIECE_TEMPLATES},
        "total_area": round(total, 2),
        "expected_area": expected,
        "ok": abs(total - expected) < 0.01,
    }
