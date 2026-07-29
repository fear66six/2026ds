from __future__ import annotations

import unittest

from _snapshot_support import make_plan
from q1.verification import PieceObservation, VerificationStatus, verify_after_place


class PlacedPieceMovedTests(unittest.TestCase):
    def test_historical_target_piece_motion_stops_flow(self):
        plan = make_plan()
        plan.pieces[0].status = "COMPLETED"
        current = plan.pieces[1]
        observations = [
            PieceObservation(
                current.template_id,
                current.target_pose_mm.center_mm,
                0.0,
                region="TARGET",
            ),
            PieceObservation("P1", (100.0, 200.0), 0.0, region="TARGET"),
        ]
        result = verify_after_place(plan, "P2", observations)
        self.assertEqual(result.status, VerificationStatus.PLACED_PIECE_MOVED)


if __name__ == "__main__":
    unittest.main()
