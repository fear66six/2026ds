from __future__ import annotations

import unittest

from _snapshot_support import make_plan
from q1.plan_manager import PoseMM, update_remaining_piece_pose
from q1.verification import VerificationResult, VerificationStatus


class RemainingPoseUpdateTests(unittest.TestCase):
    def test_updates_only_pending_source_pose(self):
        plan = make_plan()
        target_before = plan.pieces[1].target_pose_mm
        result = VerificationResult(
            VerificationStatus.PASS_WITH_SOURCE_UPDATE,
            "P1",
            "shift",
            remaining_pose_updates={"P2": PoseMM((55.0, 45.0), 2.0, [])},
        )
        updated = update_remaining_piece_pose(plan, result)
        self.assertEqual(updated.plan_version, 2)
        self.assertEqual(updated.pieces[1].template_id, "P2")
        self.assertEqual(updated.pieces[1].source_pose_mm.center_mm, (55.0, 45.0))
        self.assertIs(updated.pieces[1].target_pose_mm, target_before)


if __name__ == "__main__":
    unittest.main()
