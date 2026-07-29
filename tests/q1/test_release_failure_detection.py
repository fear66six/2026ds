from __future__ import annotations

import unittest

from _snapshot_support import make_plan
from q1.verification import PieceObservation, VerificationStatus, verify_after_place


class ReleaseFailureTests(unittest.TestCase):
    def test_piece_near_tool_is_not_accepted_as_placed(self):
        plan = make_plan()
        result = verify_after_place(
            plan,
            "P1",
            [PieceObservation("P1", (20.0, 40.0), 0.0, region="TOOL")],
        )
        self.assertEqual(result.status, VerificationStatus.RELEASE_FAILED)
        self.assertFalse(result.release_confirmed)


if __name__ == "__main__":
    unittest.main()
