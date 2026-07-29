from __future__ import annotations

from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.vision import _detect_outer_mat_frame
from q1.paper_calibration import PaperCalibrationLock, paper_from_corners


class PaperQuadTests(unittest.TestCase):
    def test_rotated_a4_is_not_replaced_by_axis_aligned_bbox(self):
        gray = np.full((520, 700), 255, np.uint8)
        rect = ((350.0, 260.0), (260.0, 368.0), 17.0)
        expected = cv2.boxPoints(rect).astype(np.int32)
        cv2.fillConvexPoly(gray, expected, 0)

        quad = _detect_outer_mat_frame(gray)

        self.assertIsNotNone(quad)
        unique_x = len(np.unique(np.rint(quad[:, 0]).astype(int)))
        unique_y = len(np.unique(np.rint(quad[:, 1]).astype(int)))
        self.assertGreater(unique_x, 2)
        self.assertGreater(unique_y, 2)
        qarea = abs(cv2.contourArea(quad.astype(np.float32)))
        x, y, width, height = cv2.boundingRect(expected)
        self.assertLess(qarea, width * height * 0.92)

    def test_auto_lock_requires_fifteen_stable_observations(self):
        shape = (520, 700, 3)
        corners = np.array(
            [[220, 50], [480, 50], [480, 418], [220, 418]],
            np.float32,
        )
        paper = paper_from_corners(corners, shape)
        lock = PaperCalibrationLock()
        lock.reset_auto()
        for _ in range(14):
            self.assertIsNone(lock.observe(paper, shape))
        self.assertIsNotNone(lock.observe(paper, shape))
        self.assertTrue(lock.status()["locked"])


if __name__ == "__main__":
    unittest.main()
