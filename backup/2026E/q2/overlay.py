"""第二问检测叠加图（可变目标矩形）"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

from . import config
from .assignment import PieceAssignment
from .vision import DetectedPiece, PaperFrame, cm_to_px as _cm_to_px


def draw_overlay_q2(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    pieces: List[DetectedPiece],
    target_origin: Tuple[float, float],
    target_size: Tuple[float, float],
    assignments: Optional[List[PieceAssignment]] = None,
) -> np.ndarray:
    out = frame.copy()
    cv2.polylines(out, [paper.corners_px.astype(np.int32)], True, (0, 255, 255), 2)

    y_px = int(
        paper.corners_px[0, 1]
        + (divider_y_cm / config.A4_HEIGHT_CM) * (paper.corners_px[3, 1] - paper.corners_px[0, 1])
    )
    cv2.line(
        out,
        (int(paper.corners_px[0, 0]), y_px),
        (int(paper.corners_px[1, 0]), y_px),
        (255, 0, 0),
        2,
    )

    ox, oy = target_origin
    tw, th = target_size
    target_pts_cm = np.array(
        [
            [ox, oy],
            [ox + tw, oy],
            [ox + tw, oy + th],
            [ox, oy + th],
        ]
    )
    target_px = [ _cm_to_px(tuple(pt), paper) for pt in target_pts_cm ]
    cv2.polylines(out, [np.array(target_px, dtype=np.int32)], True, (0, 255, 0), 2)
    cv2.putText(
        out,
        f"Target {tw:.1f}x{th:.1f} cm",
        (int(target_px[0][0]), max(20, int(target_px[0][1]) - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 0),
        1,
    )

    for i, piece in enumerate(pieces):
        color = (0, 255, 255) if piece.in_upper_half else (255, 180, 0)
        cv2.drawContours(out, [piece.contour], -1, color, 2)
        px = _cm_to_px(piece.center_cm, paper)
        cv2.putText(out, f"#{i}", (int(px[0]) - 8, int(px[1]) + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    if assignments:
        for asg in assignments:
            if len(asg.target_vertices_cm) < 3:
                continue
            pts_px = [_cm_to_px(tuple(p), paper) for p in asg.target_vertices_cm]
            cv2.polylines(out, [np.array(pts_px, dtype=np.int32)], True, (0, 200, 255), 2)

    return out
