from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.vision import PaperFrame, detect_pieces, detect_q1_live_candidates


class LiveNoOversizeSplitTests(unittest.TestCase):
    def test_large_reflection_stays_one_rejected_candidate(self):
        paper = PaperFrame(
            np.array([[80, 40], [500, 40], [500, 634], [80, 634]], np.float32),
            px_per_cm=20.0,
        )
        frame = np.zeros((680, 580, 3), np.uint8)
        cv2.rectangle(frame, (150, 100), (310, 210), (255, 255, 255), -1)
        result = detect_q1_live_candidates(
            frame, paper, 14.85, [((0, 0, 150), (180, 80, 255))]
        )
        oversized = [
            candidate
            for candidate in result["rejected_candidates"]
            if "OVERSIZED_LIVE_CANDIDATE" in candidate.rejection_reasons
        ]
        self.assertEqual(len(oversized), 1)
        self.assertEqual(result["selected_candidates"], [])

        with patch(
            "q1.vision._split_oversized_contour",
            side_effect=AssertionError("live mode must not split"),
        ):
            pieces = detect_pieces(
                frame,
                paper,
                14.85,
                [((0, 0, 150), (180, 80, 255))],
                live=True,
            )
        self.assertEqual(pieces, [])


if __name__ == "__main__":
    unittest.main()
