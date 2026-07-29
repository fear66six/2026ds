"""第二问专用视觉检测：避免碎片粘连、放宽面积上限"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .vision import (
    DetectedPiece,
    PaperFrame,
    _contour_to_cm,
    _is_divider_contour,
    _px_to_cm,
    detect_divider_line,
    detect_paper,
    resample_polygon,
)


def segment_pieces_q2(
    frame: np.ndarray,
    paper: PaperFrame,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]],
    divider_y_cm: float,
) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for low, high in hsv_ranges:
        mask |= cv2.inRange(hsv, np.array(low), np.array(high))

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # 不做 close，避免相邻碎片被桥接成一块

    border = max(3, int(paper.px_per_cm * 0.35))
    mask[:border, :] = 0
    mask[-border:, :] = 0
    mask[:, :border] = 0
    mask[:, -border:] = 0
    # 分隔线附近不在 mask 里清零，避免碎片被裁掉；上半区过滤在 detect_pieces_q2 之后做
    return mask


def _watershed_split_blob(sub: np.ndarray, n_expected: int = 2) -> np.ndarray:
    """对单个连通域做距离变换 + 分水岭分离"""
    sub = (sub > 0).astype(np.uint8) * 255
    if not np.any(sub):
        return sub

    dist = cv2.distanceTransform(sub, cv2.DIST_L2, 5)
    peak = float(dist.max())
    if peak < 4.0:
        return sub

    _, sure_fg = cv2.threshold(dist, max(2.0, 0.38 * peak), 255, 0)
    sure_fg = np.uint8(sure_fg)
    unknown = cv2.subtract(sub, sure_fg)
    _, markers = cv2.connectedComponents(sure_fg)
    if markers.max() < 2:
        return sub

    markers = markers + 1
    markers[unknown == 255] = 0
    color = cv2.cvtColor(sub, cv2.COLOR_GRAY2BGR)
    cv2.watershed(color, markers)

    out = np.zeros_like(sub)
    label_id = 2
    for lbl in range(2, markers.max() + 1):
        region = ((markers == lbl) & (sub > 0)).astype(np.uint8) * 255
        if cv2.countNonZero(region) < 80:
            continue
        out = cv2.bitwise_or(out, region)
        label_id += 1
        if label_id - 2 >= n_expected:
            break
    return out if cv2.countNonZero(out) > 0 else sub


def _split_large_blob(mask: np.ndarray, max_area_px: float) -> np.ndarray:
    """面积过大的连通域：先腐蚀，再分水岭，尽量拆成多片"""
    out = mask.copy()
    cnts, _ = cv2.findContours(out, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if area <= max_area_px:
            continue
        sub = np.zeros_like(out)
        cv2.drawContours(sub, [cnt], -1, 255, thickness=-1)

        n_parts = max(2, int(round(area / max(max_area_px, 1.0))))
        n_parts = min(n_parts, 4)

        eroded = cv2.erode(sub, np.ones((5, 5), np.uint8), iterations=2)
        split = _watershed_split_blob(sub, n_expected=n_parts)
        if cv2.countNonZero(eroded) > 0:
            split = cv2.bitwise_or(split, eroded)

        out[sub > 0] = 0
        out |= split
    return out


def detect_pieces_q2(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] | None = None,
) -> List[DetectedPiece]:
    if hsv_ranges is None:
        hsv_ranges = config.DEFAULT_HSV_RANGES

    mask = segment_pieces_q2(frame, paper, hsv_ranges, divider_y_cm)
    max_single_px = config.MAX_DETECT_PIECE_AREA_CM2 * (paper.px_per_cm**2)
    mask = _split_large_blob(mask, max_single_px * 1.15)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pieces: List[DetectedPiece] = []

    for cnt in contours:
        area_px = cv2.contourArea(cnt)
        if area_px < 120:
            continue
        area_cm2 = area_px / (paper.px_per_cm**2)
        if area_cm2 < config.MIN_PIECE_AREA_CM2_DETECT:
            continue
        if area_cm2 > config.MAX_DETECT_PIECE_AREA_CM2:
            continue

        rect = cv2.minAreaRect(cnt)
        (cx_px, cy_px), _, angle = rect
        center_cm = _px_to_cm(np.array([cx_px, cy_px]), paper)

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.025 * peri, True)
        if len(approx) < 3:
            approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        contour_cm = _contour_to_cm(cnt, paper)
        vertices_cm = _contour_to_cm(approx, paper) if len(approx) >= 3 else resample_polygon(contour_cm, 32)

        x, y, bw, bh = cv2.boundingRect(cnt)
        tl = _px_to_cm(np.array([x, y]), paper)
        br = _px_to_cm(np.array([x + bw, y + bh]), paper)
        bbox_cm = (tl[0], tl[1], br[0] - tl[0], br[1] - tl[1])

        if _is_divider_contour(bbox_cm):
            continue

        in_upper = center_cm[1] < divider_y_cm
        pieces.append(
            DetectedPiece(
                contour=cnt,
                center_cm=center_cm,
                angle_deg=float(angle),
                area_cm2=float(area_cm2),
                vertices_cm=vertices_cm,
                bbox_cm=bbox_cm,
                in_upper_half=in_upper,
            )
        )
    return pieces
