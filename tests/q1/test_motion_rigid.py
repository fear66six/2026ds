import numpy as np

from q1.analyzer import SceneAnalyzer
from q1.calibration import ArmCoordinateMapper
from q1.camera import StaticImageCamera
from q1.executors.simulation import SimulationWorld
from q1.geometry import apply_rigid_pose, normalize_angle_deg, rigid_placement_transform
from q1.motion import plan_piece_moves
from q1.pieces import template_target_vertices_mm
from q1.runtime_config import Q1RuntimeConfig


def test_rigid_placement_recovers_known_translation_and_rotation():
    origin = (0.0, 0.0)
    target = template_target_vertices_mm(0, origin)
    center = target.mean(axis=0)
    local = target - center
    source = apply_rigid_pose(local, (42.0, 18.0), 23.0)

    _, end_c, angle = rigid_placement_transform(source, target)
    assert np.linalg.norm(end_c - center) < 1.0
    assert abs(abs(normalize_angle_deg(angle)) - 23.0) < 1.5


def test_planner_uses_rigid_target_center_not_bbox_angle(tmp_path):
    world = SimulationWorld()
    snapshot = StaticImageCamera(world.snapshot).capture_snapshot(0)
    scene = SceneAnalyzer().analyze(snapshot, 0)
    plan = plan_piece_moves(
        scene,
        ArmCoordinateMapper(None),
        Q1RuntimeConfig(run_root=tmp_path),
    )[0]
    template_id = plan.template_id
    expected = scene.templates[template_id].expected_target_vertices_mm
    _, end_c, angle = rigid_placement_transform(
        np.asarray(scene.templates[template_id].detected_piece.vertices_mm),
        np.asarray(expected),
    )
    assert abs(plan.target_pose_paper.x_mm - end_c[0]) < 1.0
    assert abs(plan.target_pose_paper.y_mm - end_c[1]) < 1.0
    assert abs(plan.rotation_delta_deg - angle) < 1.5
