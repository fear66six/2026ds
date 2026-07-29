from __future__ import annotations

from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.vision import PaperFrame, detect_q1_live_candidates


class RoiBoundaryRejectTests(unittest.TestCase):
    def test_crossing_white_block_is_rejected(self):
        paper = PaperFrame(
            np.array([[80, 40], [500, 40], [500, 634], [80, 634]], np.float32),
            px_per_cm=20.0,
        )
        frame = np.zeros((680, 580, 3), np.uint8)
        cv2.rectangle(frame, (88, 100), (135, 170), (255, 255, 255), -1)
        result = detect_q1_live_candidates(
            frame, paper, 14.85, [((0, 0, 150), (180, 80, 255))]
        )
        reasons = result["rejected_candidates"][0].rejection_reasons
        self.assertIn("SAFE_INSIDE_RATIO_LOW", reasons)
        self.assertIn("TOUCHES_ROI_BORDER", reasons)
        self.assertEqual(result["selected_candidates"], [])


if __name__ == "__main__":
    unittest.main()
