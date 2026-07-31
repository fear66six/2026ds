"""Single-capture Q2 solve and motion planning workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2

from q1.calibration import ArmCoordinateMapper
from q1.workflow import write_json, write_plan_image

from .models import WhitePuzzleScene
from .motion import plan_white_puzzle_moves
from .runtime_config import Q2RuntimeConfig


def capture_and_plan(
    *,
    camera,
    analyzer,
    mapper: ArmCoordinateMapper,
    config: Q2RuntimeConfig,
    output_dir: Path,
    phase_changed: Callable[[str], None] | None = None,
) -> tuple[WhitePuzzleScene, list]:
    output_dir.mkdir(parents=True, exist_ok=True)

    if phase_changed is not None:
        phase_changed("capture")
    snapshot = camera.capture_snapshot(0)

    if phase_changed is not None:
        phase_changed("analyze")
    scene = analyzer.analyze(snapshot, 0)
    scene.timings_ms["capture_ms"] = float(
        snapshot.metadata.get("capture_burst_ms", 0.0)
    )
    scene.timings_ms["frame_selection_ms"] = float(
        snapshot.metadata.get("select_best_frame_ms", 0.0)
    )

    capture_path = output_dir / "capture.png"
    if not cv2.imwrite(str(capture_path), snapshot.frame):
        raise RuntimeError(f"CAPTURE_SAVE_FAILED: {capture_path}")
    scene.image_path = str(capture_path)
    write_json(output_dir / "scene.json", scene)

    if not scene.scene_valid:
        raise RuntimeError(
            "Q2_ANALYSIS_FAILED: exact official-size geometric solution required; "
            f"warnings={scene.warnings}"
        )
    if analyzer.last_puzzle is None or analyzer.last_solution is None:
        raise RuntimeError("Q2_ANALYSIS_STATE_MISSING")

    if phase_changed is not None:
        phase_changed("plan")
    moves = plan_white_puzzle_moves(
        analyzer.last_puzzle,
        analyzer.last_solution,
        mapper,
        config,
    )
    write_json(output_dir / "piece_moves.json", moves)
    if analyzer.last_paper is None:
        raise RuntimeError("PLAN_IMAGE_FAILED: paper transform is unavailable")
    write_plan_image(
        output_dir / "plan.png",
        snapshot.frame,
        analyzer.last_paper,
        moves,
    )
    return scene, moves

