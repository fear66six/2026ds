from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.snapshot_state import SnapshotStateMachine


class ResumeRequiresVerifyTests(unittest.TestCase):
    def test_resume_cannot_execute_before_fresh_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            machine = SnapshotStateMachine.resume("existing", root=directory)
            with self.assertRaisesRegex(RuntimeError, "REQUIRES_FRESH"):
                machine.assert_resume_verified()
            machine.mark_resume_verified()
            machine.assert_resume_verified()


if __name__ == "__main__":
    unittest.main()
