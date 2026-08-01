"""Single-capture Q2 solve and motion planning workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from q1.calibration import ArmCoordinateMapper
from q1.models import PieceMove
from q1.workflow import write_json

from .models import WhitePuzzleScene
from .motion import plan_white_puzzle_moves
from .runtime_config import Q2RuntimeConfig


def write_q2_plan_image(
    path: Path,
    rectified_bgr: np.ndarray,
    moves: list[PieceMove],
    *,
    pixels_per_mm: float,
) -> None:
    """Draw plan overlays on the same rectified frame used for detection."""

    canvas = rectified_bgr.copy()
    colors = ((42, 190, 255), (87, 215, 103), (255, 126, 70), (224, 91, 214))
    scale = float(pixels_per_mm)

    def points_px(vertices_mm: np.ndarray) -> np.ndarray:
        arr = np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 2)
        return np.rint(arr * scale).astype(np.int32).reshape(-1, 1, 2)

    def point_px(point_mm: tuple[float, float]) -> tuple[int, int]:
        return int(round(point_mm[0] * scale)), int(round(point_mm[1] * scale))

    for move in moves:
        if move.source_vertices_mm is None or move.target_vertices_mm is None:
            continue
        piece_index = int(str(move.template_id).rsplit("_", 1)[-1]) - 1
        color = colors[piece_index % len(colors)]
        source = points_px(move.source_vertices_mm)
        target = points_px(move.target_vertices_mm)
        start = point_px((move.source_pose_paper.x_mm, move.source_pose_paper.y_mm))
        end = point_px((move.target_pose_paper.x_mm, move.target_pose_paper.y_mm))
        cv2.polylines(canvas, [source], True, color, 3, cv2.LINE_AA)
        cv2.polylines(canvas, [target], True, color, 3, cv2.LINE_AA)
        cv2.arrowedLine(canvas, start, end, color, 3, cv2.LINE_AA, tipLength=0.08)
        cv2.circle(canvas, start, 6, color, -1, cv2.LINE_AA)
        cv2.circle(canvas, end, 6, color, 2, cv2.LINE_AA)
        cv2.putText(
            canvas,
            move.template_id,
            (start[0] + 8, start[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            2,
            cv2.LINE_AA,
        )

    if not cv2.imwrite(str(path), canvas):
        raise RuntimeError(f"PLAN_IMAGE_SAVE_FAILED: {path}")


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
    if analyzer.last_rectified is None:
        raise RuntimeError("PLAN_IMAGE_FAILED: rectified frame is unavailable")
    rectified_path = output_dir / "rectified.png"
    if not cv2.imwrite(str(rectified_path), analyzer.last_rectified):
        raise RuntimeError(f"RECTIFIED_SAVE_FAILED: {rectified_path}")
    write_q2_plan_image(
        output_dir / "plan.png",
        analyzer.last_rectified,
        moves,
        pixels_per_mm=analyzer.pixels_per_mm,
    )
    return scene, moves

