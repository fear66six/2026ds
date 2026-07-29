from __future__ import annotations

import unittest

from _snapshot_support import make_plan
from q1.plan_manager import PoseMM, update_remaining_piece_pose
from q1.verification import VerificationResult, VerificationStatus


class PlanVersioningTests(unittest.TestCase):
    def test_no_update_keeps_version_and_update_increments_once(self):
        plan = make_plan()
        no_change = VerificationResult(VerificationStatus.PASS, "P1", "ok")
        self.assertEqual(update_remaining_piece_pose(plan, no_change).plan_version, 1)
        change = VerificationResult(
            VerificationStatus.PASS_WITH_SOURCE_UPDATE,
            "P1",
            "move",
            remaining_pose_updates={"P3": PoseMM((1.0, 2.0), 3.0, [])},
        )
        self.assertEqual(update_remaining_piece_pose(plan, change).plan_version, 2)


if __name__ == "__main__":
    unittest.main()
