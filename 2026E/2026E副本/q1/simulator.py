"""第一问测试图合成：黑底白片 + 分散摆放"""

from __future__ import annotations

from typing import List, Tuple

import cv2
import numpy as np

from . import config
from .pieces import PIECE_TEMPLATES


def _cm_to_px(pt_cm: Tuple[float, float], px_per_cm: float, margin_px: int = 40) -> Tuple[int, int]:
    x = int(margin_px + pt_cm[0] * px_per_cm)
    y = int(margin_px + pt_cm[1] * px_per_cm)
    return x, y


def _draw_white_piece(
    img: np.ndarray,
    tpl,
    center_cm: Tuple[float, float],
    angle_deg: float,
    px_per_cm: float,
    margin: int,
) -> None:
    local0 = np.array(tpl.local_vertices, dtype=np.float64)
    c0 = local0.mean(axis=0)
    pts_local = local0 - c0
    rad = np.deg2rad(angle_deg)
    cos_a, sin_a = np.cos(rad), np.sin(rad)
    rot = np.array([[cos_a, -sin_a], [sin_a, cos_a]])
    world = pts_local @ rot.T + np.array(center_cm)

    px_pts = []
    for x, y in world:
        px, py = _cm_to_px((float(x), float(y)), px_per_cm, margin)
        px_pts.append([px, py])
    cv2.fillPoly(img, [np.array(px_pts, dtype=np.int32)], (255, 255, 255))
    cv2.polylines(img, [np.array(px_pts, dtype=np.int32)], True, (180, 180, 180), 1)


SCATTERED_LAYOUTS: dict[str, List[Tuple[Tuple[float, float], float]]] = {
    "a": [
        ((3.5, 3.0), 18.0),
        ((17.0, 3.5), -22.0),
        ((4.0, 10.5), 12.0),
        ((16.5, 9.0), -15.0),
    ],
    "b": [
        ((7.0, 2.8), -28.0),
        ((18.5, 4.5), 35.0),
        ((3.5, 8.5), -18.0),
        ((15.5, 8.0), 25.0),
    ],
}

DEFAULT_SCATTERED_LAYOUT = "b"


def generate_scattered_image(
    px_per_cm: float = 14.0,
    placements: List[Tuple[Tuple[float, float], float]] | None = None,
    layout: str = DEFAULT_SCATTERED_LAYOUT,
) -> np.ndarray:
    """黑底白片、上半区分散摆放（含旋转）"""
    w = int(config.A4_WIDTH_CM * px_per_cm + 80)
    h = int(config.A4_HEIGHT_CM * px_per_cm + 80)
    img = np.zeros((h, w, 3), dtype=np.uint8)
    margin = 40

    cv2.rectangle(img, (margin, margin), (w - margin, h - margin), (35, 35, 35), 1)

    div_y = margin + int(config.DIVIDER_Y_CM * px_per_cm)
    cv2.line(img, (margin, div_y), (w - margin, div_y), (255, 255, 255), 2)

    if placements is None:
        placements = SCATTERED_LAYOUTS.get(layout, SCATTERED_LAYOUTS[DEFAULT_SCATTERED_LAYOUT])

    for tpl, (center, angle) in zip(PIECE_TEMPLATES, placements):
        _draw_white_piece(img, tpl, center, angle, px_per_cm, margin)

    return img
