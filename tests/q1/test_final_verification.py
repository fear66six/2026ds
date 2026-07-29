from __future__ import annotations

import unittest

from _snapshot_support import make_plan
from q1.verification import PieceObservation, verify_final


class FinalVerificationTests(unittest.TestCase):
    def test_all_four_targets_are_required(self):
        plan = make_plan()
        observations = [
            PieceObservation(
                move.template_id,
                move.target_pose_mm.center_mm,
                move.target_pose_mm.angle_deg,
                move.target_pose_mm.vertices_mm,
                region="TARGET",
            )
            for move in plan.pieces
        ]
        self.assertTrue(verify_final(plan, observations).pass_fail)
        failed = verify_final(plan, observations[:-1])
        self.assertFalse(failed.pass_fail)
        self.assertEqual(failed.missing_templates, ["P4"])


if __name__ == "__main__":
    unittest.main()
