from __future__ import annotations

import cv2
import numpy as np

from q1.vision import PaperFrame, _contour_to_piece
from q1.white_segmentation import coarse_to_fine_contours


def test_full_resolution_contours_do_not_duplicate_or_lose_long_piece() -> None:
    frame = np.zeros((700, 840, 3), dtype=np.uint8)
    polygons = [
        np.array([[80, 70], [210, 70], [210, 170], [80, 170]], np.int32),
        np.array([[300, 60], [480, 60], [460, 190], [320, 180]], np.int32),
        np.array([[80, 280], [300, 280], [170, 460]], np.int32),
        np.array([[430, 250], [720, 250], [680, 500], [450, 450]], np.int32),
    ]
    for polygon in polygons:
        cv2.fillConvexPoly(frame, polygon, (245, 245, 245))
    cv2.rectangle(frame, (555, 245), (575, 285), (0, 0, 0), -1)
    cv2.line(frame, (0, 580), (839, 580), (255, 255, 255), 8)

    contours = coarse_to_fine_contours(frame)
    piece_contours = [
        contour
        for contour in contours
        if cv2.boundingRect(contour)[2] < 800
    ]

    assert len(piece_contours) == 4
    boxes = [cv2.boundingRect(contour) for contour in piece_contours]
    assert len(set(boxes)) == 4
    assert any(width > 280 and height > 240 for _, _, width, height in boxes)


def test_piece_geometry_uses_convex_outline_for_small_mask_notch() -> None:
    notched_quad = np.array(
        [
            [100, 100],
            [220, 100],
            [220, 220],
            [160, 220],
            [160, 185],
            [145, 185],
            [145, 220],
            [100, 220],
        ],
        np.int32,
    ).reshape(-1, 1, 2)
    paper = PaperFrame(
        corners_px=np.array(
            [[0, 0], [399, 0], [399, 399], [0, 399]],
            np.float32,
        ),
        px_per_cm=20.0,
    )

    piece = _contour_to_piece(notched_quad, paper, 20.0, (400, 400, 3))

    assert piece is not None
    assert len(piece.vertices_cm) == 4
    assert len(piece.contour) == 4
