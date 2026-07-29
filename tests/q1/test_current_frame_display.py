from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.camera_run import render_live_result
from q1.vision import PaperFrame


class CurrentFrameDisplayTests(unittest.TestCase):
    def test_result_is_drawn_on_new_current_frame(self):
        paper = PaperFrame(
            np.array([[5, 5], [58, 5], [58, 42], [5, 42]], np.float32),
            px_per_cm=2.0,
        )
        result = {
            "ok": True,
            "paper": paper,
            "detect_frame_shape": (48, 64, 3),
            "selected_candidates": [],
            "rejected_candidates": [],
        }
        current = np.full((48, 64, 3), 173, np.uint8)
        rendered, valid = render_live_result(current, result)
        self.assertTrue(valid)
        self.assertTrue(np.all(rendered[25, 32] == 173))


if __name__ == "__main__":
    unittest.main()
