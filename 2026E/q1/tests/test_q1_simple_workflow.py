from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np
import pytest

import q1.workflow as workflow_module
from q1.calibration import ArmCoordinateMapper
from q1.camera import StaticImageCamera
from q1.controller import Q1Controller
from q1.executors.simulation import SimulationWorld
from q1.models import ExecutionResult, SceneAnalysis, Snapshot
from q1.motion import plan_piece_moves
from q1.runtime_config import Q1RuntimeConfig
from q1.analyzer import SceneAnalyzer


@dataclass
class _Move:
    template_id: str
    cycle_index: int


class _Camera:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.capture_count = 0

    def open(self) -> None:
        self.events.append("camera.open")

    def capture_snapshot(self, cycle_index: int) -> Snapshot:
        self.events.append(f"camera.capture:{cycle_index}")
        self.capture_count += 1
        return Snapshot(
            frame=np.zeros((20, 30, 3), dtype=np.uint8),
            timestamp=0.0,
            sharpness=1.0,
            brightness=2.0,
            motion_score=0.0,
            path="",
            metadata={"capture_burst_ms": 3.0, "select_best_frame_ms": 1.0},
        )

    def close(self) -> None:
        self.events.append("camera.close")


class _Analyzer:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.analysis_count = 0

    def analyze(self, snapshot: Snapshot, cycle_index: int) -> SceneAnalysis:
        del snapshot
        self.events.append(f"analyzer.analyze:{cycle_index}")
        self.analysis_count += 1
        return SceneAnalysis(
            cycle_index=cycle_index,
            image_path="",
            pieces=[],
            templates={},
            placed_templates=set(),
            remaining_templates={"P1", "P2"},
            image_quality={},
            paper_valid=True,
            scene_valid=True,
        )


class _Robot:
    def __init__(self, events: list[str], fail_template: str | None = None) -> None:
        self.events = events
        self.fail_template = fail_template
        self.executed: list[str] = []

    def initialize(self) -> None:
        self.events.append("robot.initialize")

    def move_to_observe_pose(self) -> None:
        self.events.append("robot.observe")

    def execute_single_move(self, move: _Move, magnet) -> ExecutionResult:
        del magnet
        self.events.append(f"robot.execute:{move.template_id}")
        self.executed.append(move.template_id)
        ok = move.template_id != self.fail_template
        return ExecutionResult(ok, move.template_id, "" if ok else "test failure")

    def emergency_stop(self) -> None:
        self.events.append("robot.emergency_stop")

    def close(self) -> None:
        self.events.append("robot.close")


class _Magnet:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def initialize(self) -> None:
        self.events.append("magnet.initialize")

    def ensure_off(self) -> None:
        self.events.append("magnet.ensure_off")

    def emergency_off(self) -> None:
        self.events.append("magnet.emergency_off")

    def close(self) -> None:
        self.events.append("magnet.close")


def _build_controller(tmp_path, monkeypatch, *, fail_template=None):
    events: list[str] = []
    camera = _Camera(events)
    analyzer = _Analyzer(events)
    robot = _Robot(events, fail_template)
    magnet = _Magnet(events)
    moves = [_Move("P1", 0), _Move("P2", 1)]
    monkeypatch.setattr(
        workflow_module,
        "plan_piece_moves",
        lambda _scene, _mapper, _config: moves,
    )
    monkeypatch.setattr(
        workflow_module,
        "write_plan_image",
        lambda path, *_args: path.write_bytes(b"plan"),
    )
    analyzer.last_paper = object()
    controller = Q1Controller(
        camera=camera,
        analyzer=analyzer,
        robot=robot,
        magnet=magnet,
        mapper=object(),
        config=Q1RuntimeConfig(
            run_root=tmp_path,
            direct_pick_release_pose_verified=True,
        ),
    )
    return controller, camera, analyzer, robot, events


def test_controller_captures_and_analyzes_once_then_executes_queue(
    tmp_path, monkeypatch
) -> None:
    controller, camera, analyzer, robot, events = _build_controller(
        tmp_path, monkeypatch
    )

    controller.run()

    assert camera.capture_count == 1
    assert analyzer.analysis_count == 1
    assert robot.executed == ["P1", "P2"]
    assert events[:7] == [
        "camera.open",
        "robot.initialize",
        "magnet.initialize",
        "magnet.ensure_off",
        "robot.observe",
        "camera.capture:0",
        "analyzer.analyze:0",
    ]
    assert [path.name for path in controller.recorder.directory.glob("*.png")] == [
        "capture.png",
        "plan.png",
    ]
    assert not list(controller.recorder.directory.glob("cycle_*"))
    final = json.loads(
        (controller.recorder.directory / "final.json").read_text(encoding="utf-8")
    )
    assert final["completed"] is True
    assert final["post_move_visual_verification"] is False


def test_controller_stops_queue_after_first_failed_move(tmp_path, monkeypatch) -> None:
    controller, _, _, robot, events = _build_controller(
        tmp_path, monkeypatch, fail_template="P2"
    )

    with pytest.raises(RuntimeError, match="MOVE_FAILED"):
        controller.run()

    assert robot.executed == ["P1", "P2"]
    assert "robot.emergency_stop" in events
    assert (controller.recorder.directory / "failure.json").is_file()
    assert not (controller.recorder.directory / "final.json").exists()


def test_controller_gate_blocks_before_any_device_initialization(
    tmp_path, monkeypatch
) -> None:
    controller, _, _, robot, events = _build_controller(tmp_path, monkeypatch)
    controller.config.direct_pick_release_pose_verified = False

    with pytest.raises(RuntimeError, match="DIRECT_PICK_RELEASE_POSE_UNVERIFIED"):
        controller.run()

    assert "camera.open" not in events
    assert "robot.initialize" not in events
    assert "magnet.initialize" not in events
    assert robot.executed == []


def test_initial_scene_builds_one_ordered_p1_to_p4_queue() -> None:
    world = SimulationWorld()
    snapshot = StaticImageCamera(world.snapshot).capture_snapshot(0)
    scene = SceneAnalyzer().analyze(snapshot, 0)

    moves = plan_piece_moves(
        scene,
        ArmCoordinateMapper(None),
        Q1RuntimeConfig(),
    )

    assert [move.template_id for move in moves] == ["P1", "P2", "P3", "P4"]
    assert [move.cycle_index for move in moves] == [0, 1, 2, 3]
