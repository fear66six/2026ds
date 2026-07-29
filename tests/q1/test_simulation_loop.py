from pathlib import Path

from q1.analyzer import SceneAnalyzer
from q1.calibration import ArmCoordinateMapper
from q1.camera import StaticImageCamera
from q1.controller import Q1Controller
from q1.executors.simulation import SimulationRobotExecutor, SimulationWorld
from q1.magnet import SimulationMagnetController
from q1.runtime_config import Q1RuntimeConfig


def _run(tmp_path: Path, mode: str = "simulate"):
    world = SimulationWorld()
    robot = SimulationRobotExecutor(world)
    magnet = SimulationMagnetController()
    controller = Q1Controller(
        camera=StaticImageCamera(world.snapshot),
        analyzer=SceneAnalyzer(),
        robot=robot,
        magnet=magnet,
        mapper=ArmCoordinateMapper(None),
        config=Q1RuntimeConfig(mode=mode, run_root=tmp_path, max_cycles=12),
    )
    return controller, robot, magnet, controller.run()


def test_simulation_reaches_visual_completed_without_hardware(tmp_path: Path):
    controller, robot, magnet, final_scene = _run(tmp_path)

    assert final_scene.placed_templates == {"P1", "P2", "P3", "P4"}
    assert len(robot.executed_templates) == 4
    assert len(set(robot.executed_templates)) == 4
    assert magnet.events.count("HOLD_START") == 4
    assert magnet.events.count("HOLD_STOP") == 4
    assert not magnet.is_holding
    assert (controller.recorder.directory / "final.json").exists()
    assert (controller.recorder.directory / "events.jsonl").exists()


def test_dry_run_uses_same_state_machine(tmp_path: Path):
    controller, robot, magnet, final_scene = _run(tmp_path, "dry-run")
    assert final_scene.placed_templates == {"P1", "P2", "P3", "P4"}
    assert controller.machine.state.value == "COMPLETED"
    assert not magnet.is_holding

