from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.live_candidates import CandidateMatch, CandidateSelection, TemporalStability
from q1.pieces import PIECE_TEMPLATES
from test_fixed_four_selector import candidate


def selection(offset: float = 0.0) -> CandidateSelection:
    candidates = [
        candidate(i, template.area, len(template.local_vertices), i + 1.0 + offset)
        for i, template in enumerate(PIECE_TEMPLATES)
    ]
    return CandidateSelection(
        matches=[
            CandidateMatch(template.name, item, 0.0)
            for template, item in zip(PIECE_TEMPLATES, candidates)
        ],
        total_score=0.0,
        accepted=True,
        reason="OK",
    )


class TemporalStabilityTests(unittest.TestCase):
    def test_three_consistent_detections_required(self):
        tracker = TemporalStability()
        self.assertFalse(tracker.update(selection())["ready"])
        self.assertFalse(tracker.update(selection(0.01))["ready"])
        self.assertTrue(tracker.update(selection(0.02))["ready"])

    def test_large_motion_resets_count(self):
        tracker = TemporalStability()
        tracker.update(selection())
        tracker.update(selection())
        status = tracker.update(selection(1.0))
        self.assertFalse(status["ready"])
        self.assertEqual(status["stable_count"], 1)


if __name__ == "__main__":
    unittest.main()
