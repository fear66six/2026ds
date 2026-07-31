"""Q2 runtime configuration reusing every Q1 hardware and motion field."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from q1.runtime_config import Q1RuntimeConfig


@dataclass
class Q2RuntimeConfig(Q1RuntimeConfig):
    mode: str = "full_q2"
    authorization: str = "RUN_Q2"
    run_root: Path = Path("output/runs/q2")

    def report_metadata(self) -> dict:
        return {
            **super().report_metadata(),
            "task": "q2_white_paper_geometric_puzzle",
        }

