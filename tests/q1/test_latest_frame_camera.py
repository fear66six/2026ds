from __future__ import annotations

from pathlib import Path
import sys
import time
import unittest

Q1_ROOT = Path(__file__).resolve().parents[2] / "2026E"
sys.path.insert(0, str(Q1_ROOT))

from q1.camera_source import LatestFrameCamera
from _support import CyclingCapture


class LatestFrameCameraTests(unittest.TestCase):
    def test_latest_frame_and_clean_shutdown(self):
        cap = CyclingCapture(delay_s=0.003)
        camera = LatestFrameCamera(cap).start()
        first = camera.read_latest(wait_timeout=0.2)
        self.assertIsNotNone(first)
        time.sleep(0.03)
        latest = camera.read_latest(first.sequence, wait_timeout=0.2)
        self.assertIsNotNone(latest)
        self.assertGreater(latest.sequence, first.sequence)
        self.assertGreater(int(latest.frame[0, 0, 0]), int(first.frame[0, 0, 0]))

        repeated = camera.read_latest(latest.sequence, wait_timeout=0.0)
        self.assertTrue(repeated.repeated)
        camera.close()
        self.assertFalse(camera.thread_alive)

    def test_failure_limit_stops_thread(self):
        class FailingCapture(CyclingCapture):
            def read(self):
                return False, None

        camera = LatestFrameCamera(
            FailingCapture(),
            failure_limit=2,
            retry_delay_s=0.001,
        ).start()
        time.sleep(0.03)
        self.assertFalse(camera.thread_alive)
        self.assertGreaterEqual(camera.metrics()["failed_reads"], 2)
        camera.close()


if __name__ == "__main__":
    unittest.main()
