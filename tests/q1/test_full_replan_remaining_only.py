from __future__ import annotations

import unittest

from _snapshot_support import make_plan
from q1.plan_manager import replan_remaining_only


class FullReplanRemainingOnlyTests(unittest.TestCase):
    def test_completed_piece_is_not_returned_to_pending(self):
        plan = make_plan()
        plan.pieces[0].status = "COMPLETED"
        updated = replan_remaining_only(plan)
        self.assertEqual(updated.plan_version, 2)
        self.assertEqual(updated.pieces[0].status, "COMPLETED")
        self.assertEqual(len(updated.pending()), 3)


if __name__ == "__main__":
    unittest.main()
