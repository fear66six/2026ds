from __future__ import annotations

import cv2
import numpy as np

from q1 import config
from q1.analyzer import _roi_metrics
from q1.vision import PaperFrame, detect_paper, rectify_paper


def test_landscape_source_roi_is_image_left_not_image_top() -> None:
    paper = PaperFrame(
        corners_px=np.array(
            [[160, 30], [1130, 30], [1130, 706], [160, 706]],
            np.float32,
        ),
        px_per_cm=32.0,
        landscape_in_image=True,
    )
    lower_left_image_piece = np.array(
        [[250, 420], [420, 420], [420, 650], [250, 650]],
        np.int32,
    ).reshape(-1, 1, 2)

    touches, inside_ratio, reason = _roi_metrics(
        lower_left_image_piece,
        (720, 1280, 3),
        paper=paper,
        region="UPPER_SOURCE",
        divider_y_cm=config.DIVIDER_Y_CM,
    )

    assert not touches
    assert inside_ratio == 1.0
    assert reason is None


def test_k230_frame_detection_keeps_real_a4_left_edge() -> None:
    frame = np.full((720, 1280, 3), 230, dtype=np.uint8)
    cv2.rectangle(frame, (160, 30), (1130, 706), (15, 15, 15), -1)
    cv2.line(frame, (645, 30), (645, 706), (240, 240, 240), 8)

    paper = detect_paper(frame)

    assert config.CAMERA_CROP_LEFT_FRAC == 0.0
    assert paper is not None
    assert paper.landscape_in_image
    assert 150 <= float(paper.corners_px[:, 0].min()) <= 170


def test_landscape_paper_rectifies_to_portrait_a4() -> None:
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    paper = PaperFrame(
        corners_px=np.array(
            [[160, 30], [1130, 30], [1130, 706], [160, 706]],
            np.float32,
        ),
        px_per_cm=32.0,
        landscape_in_image=True,
    )

    rectified = rectify_paper(frame, paper)

    assert rectified.shape == (1188, 840, 3)
