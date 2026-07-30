from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

import q1.main as main_module
import q1.workflow as workflow_module
from q1 import k230_ttl_camera_adapter
from q1.models import SceneAnalysis, Snapshot


@dataclass
class _Move:
    template_id: str
    cycle_index: int


class _Camera:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def open(self) -> None:
        self.events.append("camera.open")

    def capture_snapshot(self, cycle_index: int) -> Snapshot:
        self.events.append(f"camera.capture:{cycle_index}")
        return Snapshot(
            frame=np.zeros((20, 30, 3), dtype=np.uint8),
            timestamp=0.0,
            sharpness=1.0,
            brightness=2.0,
            motion_score=0.0,
            path="",
            metadata={"capture_burst_ms": 3.0, "select_best_frame_ms": 0.0},
        )

    def close(self) -> None:
        self.events.append("camera.close")


class _Analyzer:
    def analyze(self, snapshot: Snapshot, cycle_index: int) -> SceneAnalysis:
        del snapshot
        return SceneAnalysis(
            cycle_index=cycle_index,
            image_path="",
            pieces=[],
            templates={},
            placed_templates=set(),
            remaining_templates={"P1", "P2", "P3", "P4"},
            image_quality={},
            paper_valid=True,
            scene_valid=True,
        )


def _robot_config() -> Path:
    return Path(__file__).resolve().parents[1] / "config" / "robot_config.json"


def test_plan_requires_confirmation_before_camera_creation(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "_build_camera",
        lambda *_args: pytest.fail("camera must not be created"),
    )
    args = main_module.parse_args(
        ["plan", "--robot-config", str(_robot_config())]
    )

    with pytest.raises(RuntimeError, match="CONFIRMATION_REQUIRED"):
        main_module.run_plan(args)


def test_k230_adapter_uses_tracked_jetson_driver() -> None:
    driver = k230_ttl_camera_adapter._DRIVER
    assert driver.parts[-2:] == ("k230_ttl_camera", "jetson")
    assert driver.parent.parent.name == "drivers"
    assert (driver / "k230_camera.py").is_file()
    assert (driver / "protocol.py").is_file()


def test_plan_only_uses_camera_and_writes_four_outputs(
    tmp_path, monkeypatch
) -> None:
    events: list[str] = []
    camera = _Camera(events)
    output_dir = tmp_path / "plan"
    monkeypatch.setattr(main_module, "_build_camera", lambda *_args: camera)
    monkeypatch.setattr(main_module, "_build_analyzer", lambda _config: _Analyzer())
    monkeypatch.setattr(
        workflow_module,
        "plan_piece_moves",
        lambda _scene, _mapper, _config: [
            _Move("P1", 0),
            _Move("P2", 1),
            _Move("P3", 2),
            _Move("P4", 3),
        ],
    )
    monkeypatch.setattr(
        workflow_module,
        "write_plan_image",
        lambda path, *_args: path.write_bytes(b"plan"),
    )
    monkeypatch.setattr(_Analyzer, "last_paper", object(), raising=False)
    monkeypatch.setattr(
        main_module,
        "build_controller",
        lambda _args: pytest.fail("plan must not build arm or magnet controllers"),
    )

    result = main_module.run_plan(
        main_module.parse_args(
            [
                "plan",
                "--robot-config",
                str(_robot_config()),
                "--output-dir",
                str(output_dir),
                "--confirm",
                "CAPTURE_AND_PLAN",
            ]
        )
    )

    assert result == output_dir.resolve()
    assert events == ["camera.open", "camera.capture:0", "camera.close"]
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "capture.png",
        "piece_moves.json",
        "plan.png",
        "scene.json",
    ]
    moves = json.loads(
        (output_dir / "piece_moves.json").read_text(encoding="utf-8")
    )
    assert [move["template_id"] for move in moves] == [
        "P1",
        "P2",
        "P3",
        "P4",
    ]
