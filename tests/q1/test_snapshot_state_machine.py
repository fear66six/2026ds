from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.snapshot_state import SnapshotState, SnapshotStateMachine


class SnapshotStateMachineTests(unittest.TestCase):
    def test_transitions_are_logged_with_reasons(self):
        with tempfile.TemporaryDirectory() as directory:
            machine = SnapshotStateMachine(root=directory)
            machine.transition(SnapshotState.PREVIEW, reason="start")
            machine.transition(SnapshotState.INITIAL_CAPTURE, reason="space")
            lines = (
                machine.run_dir / "execution_log.jsonl"
            ).read_text(encoding="utf-8").splitlines()
        events = [json.loads(line) for line in lines]
        self.assertEqual(events[-1]["state_to"], "INITIAL_CAPTURE")
        self.assertEqual(events[-1]["reason"], "space")


if __name__ == "__main__":
    unittest.main()
