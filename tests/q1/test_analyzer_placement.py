import numpy as np

from q1.analyzer import SceneAnalyzer
from q1.geometry import apply_rigid_pose, compute_rigid_align_error, normalize_angle_deg, rigid_placement_transform
from q1.models import PieceTaskStatus
from q1.pieces import template_target_vertices_mm


def _placed_piece_at_target(template_index: int, origin=(55.0, 168.5)):
    target = template_target_vertices_mm(template_index, origin)
    center = target.mean(axis=0)
    vertices = apply_rigid_pose(target - center, tuple(center), 0.0)
    return vertices


def test_placed_ok_uses_rigid_angle_not_min_area_rect():
    analyzer = SceneAnalyzer(
        center_tolerance_mm=5.0,
        angle_tolerance_deg=5.0,
        vertex_tolerance_mm=8.0,
    )
    origin = (55.0, 168.5)
    template_id = "P1"
    expected = template_target_vertices_mm(0, origin)
    vertices = _placed_piece_at_target(0, origin)

    from q1.models import PieceGeometry

    piece = PieceGeometry(
        detected_id=0,
        template_id=template_id,
        contour_px=np.zeros((4, 1, 2), dtype=np.int32),
        vertices_px=vertices,
        vertices_mm=vertices,
        edge_lengths_mm=[1.0, 1.0, 1.0, 1.0],
        inner_angles_deg=[90.0, 90.0, 90.0, 90.0],
        center_mm=tuple(vertices.mean(axis=0)),
        angle_deg=37.0,
        area_mm2=100.0,
        edge_fit_rmse_mm=0.0,
        template_match_score=0.1,
        confidence=0.99,
        region="LOWER_TARGET",
        touches_boundary=False,
    )
    states = analyzer._classify_templates([piece], 0)
    state = states[template_id]
    assert state.status == PieceTaskStatus.PLACED_OK
    _, rot = compute_rigid_align_error(vertices, expected)
    assert state.angle_error_deg is not None
    assert state.angle_error_deg < 1.0
    assert abs(rot) < 1.0
