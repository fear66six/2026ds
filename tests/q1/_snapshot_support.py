from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "2026E"))

from q1.plan_manager import PieceMovePlan, PoseMM, Q1ExecutionPlan


def make_plan() -> Q1ExecutionPlan:
    pieces = []
    for index, template_id in enumerate(("P1", "P2", "P3", "P4")):
        source = PoseMM((20.0 + index * 30.0, 40.0), 0.0, [])
        target = PoseMM((70.0 + index * 20.0, 180.0), 0.0, [])
        pieces.append(
            PieceMovePlan(
                index,
                template_id,
                index,
                source,
                target,
                0.0,
                source.center_mm,
                initial_confidence=0.9,
            )
        )
    return Q1ExecutionPlan(
        "test",
        "2026-07-29T00:00:00Z",
        "initial.png",
        pieces,
        ["P1", "P2", "P3", "P4"],
        {"width_mm": 100.0, "height_mm": 60.0},
        {"verify_after_each": True},
    )
