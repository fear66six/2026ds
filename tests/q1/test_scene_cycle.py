from pathlib import Path

from q1.analyzer import SceneAnalyzer
from q1.calibration import ArmCoordinateMapper
from q1.camera import StaticImageCamera
from q1.controller import Q1Controller
from q1.executors.simulation import SimulationRobotExecutor, SimulationWorld
from q1.magnet import SimulationMagnetController
from q1.runtime_config import Q1RuntimeConfig
from q1.state_machine import Q1State


def test_each_cycle_observes_captures_and_executes_only_one(tmp_path: Path):
    world = SimulationWorld(shift_after_move_template="P2")
    camera = StaticImageCamera(world.snapshot)
    robot = SimulationRobotExecutor(world)
    analyzer = SceneAnalyzer()
    controller = Q1Controller(
        camera=camera,
        analyzer=analyzer,
        robot=robot,
        magnet=SimulationMagnetController(),
        mapper=ArmCoordinateMapper(None),
        config=Q1RuntimeConfig(mode="simulate", run_root=tmp_path, max_cycles=12),
    )

    final_scene = controller.run()
    states = [event.state_to for event in controller.machine.events]

    assert len(final_scene.placed_templates) == 4
    assert robot.observe_count == camera.capture_count == analyzer.full_analysis_count
    assert robot.observe_count == len(robot.executed_templates) + 1
    assert len(robot.executed_templates) == len(set(robot.executed_templates))
    assert states[-2:] == [Q1State.FINAL_VERIFY.value, Q1State.COMPLETED.value]
    for cycle in range(4):
        cycle_states = [event.state_to for event in controller.machine.events if event.cycle_index == cycle]
        assert cycle_states.index(Q1State.MOVE_TO_OBSERVE.value) < cycle_states.index(Q1State.CAPTURE_SCENE.value if cycle == 0 else Q1State.VERIFY_CAPTURE.value)
        assert cycle_states.count(Q1State.PLAN_SINGLE_MOVE.value) == 1

