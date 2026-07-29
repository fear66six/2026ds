from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_ROOT = PROJECT_ROOT / "2026E"
BASELINE_ROOT = PROJECT_ROOT / "backup" / "2026E"
TEST_IMAGE = BASELINE_ROOT / "test.png"

PROBE = r"""
import cv2, json, sys
from q1.pipeline import run_pipeline
frame = cv2.imread(sys.argv[1])
result = run_pipeline(frame, verbose=False)
print(json.dumps({
    "ok": result.get("ok"),
    "pieces": len(result.get("pieces", [])),
    "assembly_ok": result.get("evaluation", {}).get("assembly_ok"),
    "max_error": result.get("evaluation", {}).get("max_vertex_error_cm"),
    "centers": [
        [round(float(value), 6) for value in piece.center_cm]
        for piece in result.get("pieces", [])
    ],
}, sort_keys=True))
"""


def run_probe(package_root: Path) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(package_root)
    output = subprocess.check_output(
        [sys.executable, "-c", PROBE, str(TEST_IMAGE)],
        env=env,
        text=True,
        encoding="utf-8",
    )
    return json.loads(output.strip().splitlines()[-1])


class PipelineRegressionTests(unittest.TestCase):
    @unittest.skipUnless(
        (BASELINE_ROOT / "q1").exists() and TEST_IMAGE.exists(),
        "pre-change q1 backup is unavailable",
    )
    def test_offline_pipeline_matches_pre_change_backup(self):
        self.assertEqual(run_probe(CURRENT_ROOT), run_probe(BASELINE_ROOT))


if __name__ == "__main__":
    unittest.main()
