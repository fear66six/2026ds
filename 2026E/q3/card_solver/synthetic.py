"""Deterministic synthetic Q3 board used by the demo and regression tests."""

from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np


def _card_face(width: int, height: int) -> np.ndarray:
    image = np.full((height, width, 3), 248, dtype=np.uint8)
    scale = min(width / 100.0, height / 70.0)
    cv2.rectangle(image, (2, 2), (width - 3, height - 3), (180, 180, 180), 2)
    cv2.ellipse(
        image,
        (width // 2, height // 2),
        (int(24 * scale), int(19 * scale)),
        18,
        0,
        360,
        (30, 30, 210),
        thickness=max(6, int(4 * scale)),
        lineType=cv2.LINE_AA,
    )
    cv2.line(
        image,
        (int(8 * scale), int(9 * scale)),
        (width - int(8 * scale), height - int(10 * scale)),
        (20, 20, 20),
        max(3, int(1.5 * scale)),
        cv2.LINE_AA,
    )
    cv2.putText(
        image,
        "Q3",
        (int(8 * scale), int(38 * scale)),
        cv2.FONT_HERSHEY_DUPLEX,
        max(0.8, 0.9 * scale),
        (15, 15, 15),
        max(2, int(1.2 * scale)),
        cv2.LINE_AA,
    )
    cv2.circle(
        image,
        (int(78 * scale), int(18 * scale)),
        int(7 * scale),
        (20, 20, 215),
        thickness=cv2.FILLED,
        lineType=cv2.LINE_AA,
    )
    return image


def create_synthetic_board(
    path: str | Path | None = None,
    *,
    pixels_per_mm: float = 5.0,
) -> np.ndarray:
    """Create four scattered textured rectangles on a portrait A4 board."""

    board_width_mm, board_height_mm = 210.0, 297.0
    width = int(round(board_width_mm * pixels_per_mm))
    height = int(round(board_height_mm * pixels_per_mm))
    board = np.full((height, width, 3), 18, dtype=np.uint8)
    divider_y = int(round(board_height_mm * 0.5 * pixels_per_mm))
    cv2.line(board, (0, divider_y), (width - 1, divider_y), (230, 230, 230), 3)

    card_width_mm, card_height_mm = 100.0, 70.0
    card = _card_face(
        int(round(card_width_mm * pixels_per_mm)),
        int(round(card_height_mm * pixels_per_mm)),
    )
    pieces = (
        (0.0, 0.0, 50.0, 35.0),
        (50.0, 0.0, 100.0, 35.0),
        (0.0, 35.0, 50.0, 70.0),
        (50.0, 35.0, 100.0, 70.0),
    )
    centres = ((35.0, 30.0), (105.0, 30.0), (35.0, 105.0), (105.0, 105.0))
    rotations_deg = (0.0, 180.0, 180.0, 0.0)

    for bounds, destination_centre, angle_deg in zip(pieces, centres, rotations_deg):
        x0, y0, x1, y1 = bounds
        source_mask = np.zeros(card.shape[:2], dtype=np.uint8)
        cv2.rectangle(
            source_mask,
            (int(round(x0 * pixels_per_mm)), int(round(y0 * pixels_per_mm))),
            (int(round(x1 * pixels_per_mm)) - 1, int(round(y1 * pixels_per_mm)) - 1),
            255,
            thickness=cv2.FILLED,
        )
        centre = np.asarray(((x0 + x1) / 2.0, (y0 + y1) / 2.0), dtype=float)
        angle = math.radians(angle_deg)
        cosine, sine = math.cos(angle), math.sin(angle)

        def mapped(point_mm: tuple[float, float]) -> tuple[float, float]:
            offset = np.asarray(point_mm, dtype=float) - centre
            rotated = np.asarray(
                (cosine * offset[0] - sine * offset[1], sine * offset[0] + cosine * offset[1])
            )
            destination = np.asarray(destination_centre) + rotated
            return tuple(destination * pixels_per_mm)

        source_points = np.asarray(
            (
                (x0 * pixels_per_mm, y0 * pixels_per_mm),
                (x1 * pixels_per_mm, y0 * pixels_per_mm),
                (x0 * pixels_per_mm, y1 * pixels_per_mm),
            ),
            dtype=np.float32,
        )
        destination_points = np.asarray(
            (mapped((x0, y0)), mapped((x1, y0)), mapped((x0, y1))),
            dtype=np.float32,
        )
        affine = cv2.getAffineTransform(source_points, destination_points)
        warped_texture = cv2.warpAffine(card, affine, (width, height), flags=cv2.INTER_LINEAR)
        warped_mask = cv2.warpAffine(
            source_mask, affine, (width, height), flags=cv2.INTER_NEAREST
        )
        board[warped_mask > 0] = warped_texture[warped_mask > 0]

    if path is not None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output), board):
            raise OSError(f"could not write synthetic image: {output}")
    return board
