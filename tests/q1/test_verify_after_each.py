from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.snapshot_state import SnapshotStateMachine
from q1.snapshot_workflow import run_snapshot_workflow


class VerifyAfterEachTests(unittest.TestCase):
    def test_four_moves_have_four_snapshot_verifications(self):
        image = cv2.imread(
            str(Path(__file__).resolve().parents[2] / "backup/2026E/test.png")
        )
        with tempfile.TemporaryDirectory() as directory:
            machine = SnapshotStateMachine(root=directory)
            result = run_snapshot_workflow(
                image,
                simulate=True,
                state_machine=machine,
            )
        self.assertTrue(result.ok)
        self.assertEqual(len(result.verifications), 4)
        self.assertTrue(all(item.release_confirmed for item in result.verifications))
        self.assertEqual(result.state, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
