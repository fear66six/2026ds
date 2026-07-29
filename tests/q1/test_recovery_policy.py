from pathlib import Path

import pytest

from q1.analyzer import SceneAnalyzer
from q1.auditor import audit_scene
from q1.calibration import ArmCoordinateMapper
from q1.camera import StaticImageCamera
from q1.controller import Q1Controller
from q1.executors.simulation import SimulationRobotExecutor, SimulationWorld
from q1.magnet import SimulationMagnetController
from q1.runtime_config import Q1RuntimeConfig
from q1.selector import select_next_piece


def _controller(world: SimulationWorld, tmp_path: Path):
    robot = SimulationRobotExecutor(world)
    magnet = SimulationMagnetController()
    controller = Q1Controller(
        camera=StaticImageCamera(world.snapshot),
        analyzer=SceneAnalyzer(),
        robot=robot,
        magnet=magnet,
        mapper=ArmCoordinateMapper(None),
        config=Q1RuntimeConfig(mode="simulate", run_root=tmp_path, max_cycles=14),
    )
    return controller, robot, magnet


def test_release_failure_automatically_recovers(tmp_path: Path):
    world = SimulationWorld()
    initial = SceneAnalyzer().analyze(StaticImageCamera(world.snapshot).capture_snapshot(0), 0)
    selected, _ = select_next_piece(initial, audit_scene(initial, None, None))
    world.release_failure_template = selected
    controller, robot, magnet = _controller(world, tmp_path)

    final_scene = controller.run()

    assert len(final_scene.placed_templates) == 4
    assert any(phase.startswith("RELEASE_RECOVERY_") for phase in robot.phase_log)
    assert not magnet.is_holding


def test_place_offset_is_seen_and_corrected_from_new_snapshot(tmp_path: Path):
    world = SimulationWorld()
    initial = SceneAnalyzer().analyze(StaticImageCamera(world.snapshot).capture_snapshot(0), 0)
    selected, _ = select_next_piece(initial, audit_scene(initial, None, None))
    world.place_offset_template = selected
    controller, robot, _ = _controller(world, tmp_path)

    final_scene = controller.run()

    assert len(final_scene.placed_templates) == 4
    assert robot.executed_templates.count(selected) == 2


def test_magnet_context_forces_off_on_exception():
    magnet = SimulationMagnetController()
    magnet.initialize()
    with pytest.raises(RuntimeError):
        with magnet.hold_session():
            assert magnet.is_holding
            raise RuntimeError("injected")
    assert not magnet.is_holding
    assert "EMERGENCY_OFF" in magnet.events

