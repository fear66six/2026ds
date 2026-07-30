"""Single-capture Q1 vision and planning workflow."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from .calibration import ArmCoordinateMapper
from .models import PieceMove, SceneAnalysis
from .motion import plan_piece_moves
from .runtime_config import Q1RuntimeConfig
from .vision import cm_to_px


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(jsonable(value), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_plan_image(
    path: Path,
    frame: np.ndarray,
    paper,
    moves: list[PieceMove],
) -> None:
    canvas = frame.copy()
    colors = ((42, 190, 255), (87, 215, 103), (255, 126, 70), (224, 91, 214))

    def points_px(vertices_mm: np.ndarray) -> np.ndarray:
        points = [
            cm_to_px((float(x) / 10.0, float(y) / 10.0), paper)
            for x, y in np.asarray(vertices_mm, dtype=np.float64).reshape(-1, 2)
        ]
        return np.rint(points).astype(np.int32).reshape(-1, 1, 2)

    def point_px(point_mm: tuple[float, float]) -> tuple[int, int]:
        x, y = cm_to_px(
            (float(point_mm[0]) / 10.0, float(point_mm[1]) / 10.0),
            paper,
        )
        return int(round(x)), int(round(y))

    for index, move in enumerate(moves):
        if move.source_vertices_mm is None or move.target_vertices_mm is None:
            continue
        color = colors[index % len(colors)]
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
    config: Q1RuntimeConfig,
    output_dir: Path,
    phase_changed: Callable[[str], None] | None = None,
) -> tuple[SceneAnalysis, list[PieceMove]]:
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
            "ANALYSIS_FAILED: image must contain a complete A4 frame and "
            f"one-to-one P1/P2/P3/P4 assignments; warnings={scene.warnings}"
        )

    if phase_changed is not None:
        phase_changed("plan")
    moves = plan_piece_moves(scene, mapper, config)
    write_json(output_dir / "piece_moves.json", moves)
    paper = getattr(analyzer, "last_paper", None)
    if paper is None:
        raise RuntimeError("PLAN_IMAGE_FAILED: paper transform is unavailable")
    write_plan_image(output_dir / "plan.png", snapshot.frame, paper, moves)
    return scene, moves
