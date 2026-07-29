from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.initial_analyzer import analyze_initial_snapshot
from q1.camera_run import run_camera_q1
from q1.snapshot_capture import SnapshotResult
from q1.snapshot_state import SnapshotStateMachine


class InitialSnapshotPlanTests(unittest.TestCase):
    def test_historical_image_produces_fixed_four_plan(self):
        image = cv2.imread(
            str(Path(__file__).resolve().parents[2] / "backup/2026E/test.png")
        )
        self.assertIsNotNone(image)
        result = analyze_initial_snapshot(image, run_id="test")
        self.assertTrue(result.ok, result.failure_reasons)
        self.assertEqual(len(result.valid_pieces), 4)
        self.assertEqual(
            {item.template_id for item in result.template_assignments},
            {"P1", "P2", "P3", "P4"},
        )
        self.assertEqual(len(result.initial_plan.pieces), 4)

    def test_space_always_starts_snapshot_without_on_run(self):
        frame = np.indices((120, 160)).sum(axis=0).astype(np.uint8)
        frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)

        class Capture:
            def read(self):
                return True, frame.copy()

        class Workflow:
            ok = True
            state = "PLAN_READY"
            run_id = "test"
            analysis = None
            failure_reason = None

        pipeline_calls = []

        def forbidden_pipeline(*args, **kwargs):
            pipeline_calls.append((args, kwargs))
            raise AssertionError("preview must not run the complete pipeline")

        with tempfile.TemporaryDirectory() as directory:
            machine = SnapshotStateMachine(root=directory)
            with (
                patch("q1.camera_run._show", side_effect=[ord(" "), ord("q")]),
                patch("q1.camera_run.SnapshotStateMachine", return_value=machine),
                patch(
                    "q1.camera_run.capture_snapshot",
                    return_value=SnapshotResult(
                        True, frame.copy(), 0, [], image_path="initial_raw.png"
                    ),
                ) as capture,
                patch(
                    "q1.camera_run.run_snapshot_workflow",
                    return_value=Workflow(),
                ) as workflow,
            ):
                result = run_camera_q1(
                    Capture(),
                    forbidden_pipeline,
                    [((0, 0, 100), (180, 100, 255))],
                    use_threaded_capture=False,
                    simulate=False,
                )
        self.assertEqual(result.state, "PLAN_READY")
        capture.assert_called_once()
        workflow.assert_called_once()
        self.assertEqual(pipeline_calls, [])


if __name__ == "__main__":
    unittest.main()
