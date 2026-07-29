from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.live_candidates import Q1Candidate, select_q1_four_candidates
from q1.pieces import PIECE_TEMPLATES
from q1.vision import DetectedPiece


def candidate(candidate_id: int, area: float, vertices: int, x: float) -> Q1Candidate:
    contour = np.array([[[0, 0]], [[10, 0]], [[10, 10]], [[0, 10]]], np.int32)
    piece = DetectedPiece(
        contour=contour,
        center_cm=(x, 5.0),
        angle_deg=0.0,
        area_cm2=area,
        vertices_cm=np.zeros((vertices, 2)),
        bbox_cm=(0.0, 0.0, 1.0, 1.0),
        in_upper_half=True,
    )
    return Q1Candidate(
        candidate_id=candidate_id,
        contour=contour,
        area_cm2=area,
        vertex_count=vertices,
        solidity=0.98,
        compactness=0.7,
        mean_gray=240.0,
        border_distance_px=50.0,
        safe_inside_ratio=1.0,
        touches_border=False,
        center_px=(x * 10, 50.0),
        piece=piece,
    )


class FixedFourSelectorTests(unittest.TestCase):
    def test_selects_templates_not_largest_four(self):
        good = [
            candidate(i, template.area, len(template.local_vertices), i + 1.0)
            for i, template in enumerate(PIECE_TEMPLATES)
        ]
        distractors = [candidate(10, 28.0, 7, 10.0), candidate(11, 15.0, 8, 11.0)]
        result = select_q1_four_candidates(good + distractors)
        self.assertTrue(result.accepted)
        self.assertEqual(
            {item.candidate.candidate_id for item in result.matches},
            {0, 1, 2, 3},
        )

    def test_bad_match_does_not_force_four(self):
        bad = [candidate(i, 29.0 - i, 8, i + 1.0) for i in range(5)]
        result = select_q1_four_candidates(bad)
        self.assertFalse(result.accepted)
        self.assertNotEqual(result.reason, "OK")


if __name__ == "__main__":
    unittest.main()
