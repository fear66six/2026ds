from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

import numpy as np

Q1_ROOT = Path(__file__).resolve().parents[2] / "2026E"
sys.path.insert(0, str(Q1_ROOT))

from q1.camera_run import render_live_result
from q1.camera_source import LatestFrameCamera
from q1.live_detect import LiveDetector
from q1.vision import PaperFrame
from _support import CyclingCapture


def result_for_shape(shape):
    h, w = shape[:2]
    return {
        "ok": True,
        "paper": PaperFrame(
            np.array([[5, 5], [w - 6, 5], [w - 6, h - 6], [5, h - 6]], np.float32),
            px_per_cm=2.0,
        ),
        "divider_y_cm": 14.85,
        "pieces": [],
        "all_pieces": [],
        "evaluation": {"assembly_ok": False},
        "detect_frame_shape": shape,
    }


class OverlayCurrentFrameTests(unittest.TestCase):
    def test_background_is_current_frame_not_old_overlay(self):
        current = np.full((100, 120, 3), 173, np.uint8)
        preview, valid = render_live_result(current, result_for_shape(current.shape))
        self.assertTrue(valid)
        unchanged_pixels = np.all(preview == 173, axis=2)
        self.assertGreater(int(unchanged_pixels.sum()), current.shape[0] * current.shape[1] // 2)

    def test_incompatible_aspect_ratio_is_ignored(self):
        current = np.full((100, 200, 3), 91, np.uint8)
        preview, valid = render_live_result(
            current,
            result_for_shape((100, 100, 3)),
        )
        self.assertFalse(valid)
        np.testing.assert_array_equal(preview, current)

    def test_slow_detection_does_not_stop_frame_sequence(self):
        def detector_fn(frame, _hsv, **_kwargs):
            time.sleep(0.3)
            return result_for_shape(frame.shape)

        camera = LatestFrameCamera(CyclingCapture(delay_s=0.005)).start()
        detector = LiveDetector([], detector_fn=detector_fn, min_interval_s=0.0)
        sequences = []
        last = None
        started = time.perf_counter()
        try:
            while len(sequences) < 20 and time.perf_counter() - started < 1.0:
                latest = camera.read_latest(last, wait_timeout=0.05)
                if latest is None or latest.repeated:
                    continue
                last = latest.sequence
                sequences.append(last)
                detector.submit(latest.frame)
            self.assertEqual(len(sequences), 20)
            self.assertTrue(all(b > a for a, b in zip(sequences, sequences[1:])))
            _result, metrics = detector.snapshot()
            self.assertGreater(metrics["submitted_frames"], metrics["processed_frames"])
        finally:
            camera.close()
            detector.close()


if __name__ == "__main__":
    unittest.main()
