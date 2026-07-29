"""检测后轮廓 refinement：保留凹多边形，禁止凸包"""

from __future__ import annotations

from typing import List

import cv2
import numpy as np

from .vision import DetectedPiece, PaperFrame, _px_to_cm, contour_to_cm


def _approx_contour(cnt: np.ndarray, max_vertices: int = 5) -> np.ndarray:
    peri = cv2.arcLength(cnt, True)
    for ratio in (0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10):
        approx = cv2.approxPolyDP(cnt, ratio * peri, True)
        if 3 <= len(approx) <= max_vertices:
            return approx
    approx = cv2.approxPolyDP(cnt, 0.10 * peri, True)
    return approx if len(approx) >= 3 else cnt


def refine_detected_pieces(pieces: List[DetectedPiece], paper: PaperFrame) -> List[DetectedPiece]:
    out: List[DetectedPiece] = []
    for p in pieces:
        cnt = p.contour
        approx = _approx_contour(cnt, max_vertices=6)
        vertices_cm = contour_to_cm(approx, paper) if len(approx) >= 3 else p.vertices_cm

        area_px = cv2.contourArea(cnt)
        M = cv2.moments(cnt)
        if abs(M["m00"]) > 1e-6:
            cx_px = M["m10"] / M["m00"]
            cy_px = M["m01"] / M["m00"]
        else:
            cx_px, cy_px = p.center_cm[0] * paper.px_per_cm, p.center_cm[1] * paper.px_per_cm
        center_cm = _px_to_cm(np.array([cx_px, cy_px]), paper)
        area_cm2 = float(area_px / (paper.px_per_cm**2))

        x, y, bw, bh = cv2.boundingRect(cnt)
        tl = _px_to_cm(np.array([x, y]), paper)
        br = _px_to_cm(np.array([x + bw, y + bh]), paper)
        bbox_cm = (float(tl[0]), float(tl[1]), float(br[0] - tl[0]), float(br[1] - tl[1]))

        out.append(
            DetectedPiece(
                contour=cnt,
                center_cm=center_cm,
                angle_deg=p.angle_deg,
                area_cm2=area_cm2,
                vertices_cm=vertices_cm,
                bbox_cm=bbox_cm,
                in_upper_half=p.in_upper_half,
            )
        )
    return out
