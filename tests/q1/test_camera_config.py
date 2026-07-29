from __future__ import annotations

from pathlib import Path
import sys
import unittest

import cv2

Q1_ROOT = Path(__file__).resolve().parents[2] / "2026E"
sys.path.insert(0, str(Q1_ROOT))

from q1.camera_source import backend_candidates, configure_camera, make_gstreamer_pipeline
from _support import CyclingCapture


class CameraConfigTests(unittest.TestCase):
    def test_requested_camera_properties_are_set_and_reported(self):
        cap = CyclingCapture()
        result = configure_camera(
            cap,
            width=640,
            height=480,
            fps=30,
            fourcc="MJPG",
            print_diagnostics=False,
        )
        self.assertEqual(cap.props[cv2.CAP_PROP_FRAME_WIDTH], 640)
        self.assertEqual(cap.props[cv2.CAP_PROP_FRAME_HEIGHT], 480)
        self.assertEqual(cap.props[cv2.CAP_PROP_FPS], 30)
        self.assertEqual(cap.props[cv2.CAP_PROP_BUFFERSIZE], 1)
        self.assertEqual(result["actual"]["backend"], "FAKE")

    def test_platform_backend_selection(self):
        self.assertEqual(backend_candidates("auto", "win32")[0], cv2.CAP_DSHOW)
        self.assertEqual(backend_candidates("auto", "linux")[0], cv2.CAP_V4L2)

    def test_gstreamer_pipeline_drops_old_buffers(self):
        pipeline = make_gstreamer_pipeline(0, 640, 480, 30, "MJPG")
        self.assertIn("drop=true", pipeline)
        self.assertIn("max-buffers=1", pipeline)
        self.assertIn("sync=false", pipeline)


if __name__ == "__main__":
    unittest.main()
