from __future__ import annotations

from pathlib import Path
import sys
import unittest

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.vision import PaperFrame, build_q1_upper_safe_roi, detect_q1_live_candidates


def paper() -> PaperFrame:
    return PaperFrame(
        np.array([[80, 40], [500, 40], [500, 634], [80, 634]], np.float32),
        px_per_cm=20.0,
    )


class UpperSafeRoiTests(unittest.TestCase):
    def test_roi_is_inset_and_excludes_lower_half(self):
        item = paper()
        roi = build_q1_upper_safe_roi(item, 14.85, (680, 580, 3))
        self.assertEqual(int(roi[45, 85]), 0)
        self.assertEqual(int(roi[100, 150]), 255)
        self.assertEqual(int(roi[360, 150]), 0)

    def test_lower_white_block_is_not_selected(self):
        item = paper()
        frame = np.zeros((680, 580, 3), np.uint8)
        cv2.rectangle(frame, (180, 410), (300, 500), (255, 255, 255), -1)
        cv2.rectangle(frame, (515, 100), (565, 170), (255, 255, 255), -1)
        result = detect_q1_live_candidates(
            frame, item, 14.85, [((0, 0, 150), (180, 80, 255))]
        )
        self.assertEqual(result["selected_candidates"], [])
        reasons = {
            reason
            for candidate in result["rejected_candidates"]
            for reason in candidate.rejection_reasons
        }
        self.assertIn("CENTER_OUTSIDE_ROI", reasons)
        self.assertIn("BBOX_OUTSIDE_A4", reasons)


if __name__ == "__main__":
    unittest.main()
