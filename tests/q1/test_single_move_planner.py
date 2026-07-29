from pathlib import Path

from q1.analyzer import SceneAnalyzer
from q1.calibration import ArmCoordinateMapper
from q1.camera import StaticImageCamera
from q1.motion import plan_single_move
from q1.runtime_config import Q1RuntimeConfig
from q1.selector import select_next_piece
from q1.auditor import audit_scene
from q1.executors.simulation import SimulationWorld


def test_selector_is_dynamic_and_planner_returns_one_unmapped_move(tmp_path: Path):
    world = SimulationWorld()
    world.pieces["P1"]["confidence"] = 0.05
    camera = StaticImageCamera(world.snapshot)
    snapshot = camera.capture_snapshot(0)
    scene = SceneAnalyzer().analyze(snapshot, 0)
    audit = audit_scene(scene, None, None)

    selected, details = select_next_piece(scene, audit)
    plan = plan_single_move(
        scene,
        selected,
        ArmCoordinateMapper(None),
        Q1RuntimeConfig(run_root=tmp_path),
        reason_selected=details["reason"],
    )

    assert selected != "P1"
    assert plan.template_id == selected
    assert plan.source_pose_robot is None
    assert plan.target_pose_robot is None
    assert details["reason"] == "DYNAMIC_LOOKAHEAD"


def test_real_run_has_no_fake_coordinate_defaults():
    blockers = Q1RuntimeConfig(mode="run").real_run_blockers()
    assert any("CALIBRATION_REQUIRED" in item for item in blockers)
    assert any("安全高度" in item for item in blockers)
    assert any("工作区" in item for item in blockers)

