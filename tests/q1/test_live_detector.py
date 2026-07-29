from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

import numpy as np

Q1_ROOT = Path(__file__).resolve().parents[2] / "2026E"
sys.path.insert(0, str(Q1_ROOT))

from q1.live_detect import LiveDetector
from q1.vision import PaperFrame


def slow_detector(frame, _hsv, **_kwargs):
    time.sleep(0.12)
    h, w = frame.shape[:2]
    paper = PaperFrame(
        np.array([[1, 1], [w - 2, 1], [w - 2, h - 2], [1, h - 2]], np.float32),
        px_per_cm=2.0,
    )
    return {
        "ok": True,
        "paper": paper,
        "divider_y_cm": 14.85,
        "pieces": [],
        "all_pieces": [],
        "lower_piece_count": 0,
        "evaluation": {"assembly_ok": False},
        "overlay": np.zeros_like(frame),
    }


class LiveDetectorTests(unittest.TestCase):
    def test_pending_frame_is_replaced_and_metrics_are_reported(self):
        detector = LiveDetector(
            [],
            detector_fn=slow_detector,
            min_interval_s=0.0,
        )
        try:
            for value in range(12):
                detector.submit(np.full((48, 64, 3), value, np.uint8))
                time.sleep(0.005)
            time.sleep(0.3)
            result, metrics = detector.snapshot()
            self.assertTrue(result["ok"])
            self.assertNotIn("overlay", result)
            self.assertEqual(result["detect_frame_shape"], (48, 64, 3))
            self.assertEqual(metrics["submitted_frames"], 12)
            self.assertGreater(metrics["dropped_frames"], 0)
            self.assertLess(metrics["processed_frames"], metrics["submitted_frames"])
            self.assertGreater(metrics["last_detect_ms"], 100)

            result["evaluation"]["assembly_ok"] = True
            again, _ = detector.snapshot()
            self.assertFalse(again["evaluation"]["assembly_ok"])
        finally:
            detector.close()
        self.assertFalse(detector.thread_alive)

    def test_exception_is_visible_and_thread_survives(self):
        calls = 0

        def flaky(frame, hsv, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("synthetic failure")
            return slow_detector(frame, hsv, **kwargs)

        detector = LiveDetector([], detector_fn=flaky, min_interval_s=0.0)
        try:
            detector.submit(np.zeros((48, 64, 3), np.uint8))
            time.sleep(0.05)
            result, metrics = detector.snapshot()
            self.assertFalse(result["ok"])
            self.assertIn("synthetic failure", metrics["last_exception"])
            self.assertTrue(metrics["thread_alive"])

            detector.submit(np.ones((48, 64, 3), np.uint8))
            time.sleep(0.2)
            result, metrics = detector.snapshot()
            self.assertTrue(result["ok"])
            self.assertIsNone(metrics["last_exception"])
        finally:
            detector.close()


if __name__ == "__main__":
    unittest.main()
