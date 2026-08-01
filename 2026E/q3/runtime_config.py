"""Q3 runtime configuration reusing every Q1 hardware and motion field."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from q1.runtime_config import Q1RuntimeConfig


@dataclass
class Q3RuntimeConfig(Q1RuntimeConfig):
    mode: str = "full_q3"
    authorization: str = "RUN_Q3"
    run_root: Path = Path("output/runs/q3")
    card_layout: str = "auto"

    def report_metadata(self) -> dict:
        return {
            **super().report_metadata(),
            "task": "q3_playing_card",
            "card_layout": self.card_layout,
        }

    def planning_blockers(self) -> list[str]:
        blockers = super().planning_blockers()
        if self.card_layout not in {"auto", "top-bottom", "left-right"}:
            blockers.append(f"INVALID_CARD_LAYOUT: {self.card_layout}")
        return blockers

