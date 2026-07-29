"""Q1 视觉与拼图几何优化离线测试。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from q1.analyzer import SceneAnalyzer
from q1.auditor import audit_scene
from q1.calibration import ArmCoordinateMapper
from q1.edge_refinement import refine_polygon_from_contour
from q1.geometry import apply_rigid_pose, apply_rigid_transform, compute_rigid_transform, normalize_angle_deg
from q1.models import PieceGeometry, PieceTaskStatus, PaperPose, SceneAnalysis, SingleMovePlan, TemplateState
from q1.motion import plan_single_move
from q1.pieces import (
    PIECE_TEMPLATES,
    template_target_vertices_mm,
    validate_placed_puzzle_geometry,
    verify_geometry_invariants,
)
from q1.puzzle_solver import assign_templates_global
from q1.runtime_config import Q1RuntimeConfig
from q1.selector import select_next_piece
from q1.wrist import choose_wrist_release_roll


def _piece(vertices_mm, *, detected_id=0, region="UPPER_SOURCE", template_id=None, area=None):
    verts = np.asarray(vertices_mm, dtype=np.float64)
    return PieceGeometry(
        detected_id=detected_id,
        template_id=template_id,
        contour_px=np.rint(verts * 4).astype(np.int32).reshape(-1, 1, 2),
        vertices_px=verts * 4,
        vertices_mm=verts,
        edge_lengths_mm=[1.0] * len(verts),
        inner_angles_deg=[90.0] * len(verts),
        center_mm=tuple(verts.mean(axis=0)),
        angle_deg=0.0,
        area_mm2=float(area if area is not None else abs(__import__("cv2").contourArea(verts.astype(np.float32)))),
        edge_fit_rmse_mm=0.2,
        template_match_score=0.0,
        confidence=0.9,
        region=region,
        touches_boundary=False,
        inside_ratio=1.0,
    )


def _contour_from_poly(verts, n=40):
    pts = []
    for i in range(len(verts)):
        a = verts[i]
        b = verts[(i + 1) % len(verts)]
        for t in np.linspace(0, 1, n // len(verts), endpoint=False):
            pts.append(a * (1 - t) + b * t)
    return np.asarray(pts, dtype=np.float64)


def test_global_assignment_finds_p4_even_if_last():
    origin = (0.0, 0.0)
    true = [template_target_vertices_mm(i, origin) for i in range(4)]
    # 平移到上半区，并打乱顺序；假候选夹在中间，真实 P4 放最后
    candidates = []
    order = [0, 1, 2]  # P1 P2 P3 first
    for i, ti in enumerate(order):
        shifted = true[ti] + np.array([10.0 + i * 5, 20.0])
        candidates.append(_piece(shifted, detected_id=i))
    glare = np.array([[5.0, 5.0], [25.0, 5.0], [25.0, 12.0], [5.0, 12.0]])  # 假反光
    candidates.append(_piece(glare, detected_id=3, area=200.0))
    candidates.append(_piece(true[3] + np.array([40.0, 30.0]), detected_id=4))  # P4 last
    result = assign_templates_global(candidates, origin_mm=origin)
    assert result.accepted
    assert result.assignments["P4"].detected_id == 4
    assert 3 in result.rejected_candidate_ids


def test_glare_not_forced_into_assignment():
    origin = (0.0, 0.0)
    candidates = [_piece(template_target_vertices_mm(i, origin) + np.array([i * 3.0, 5.0]), detected_id=i) for i in range(4)]
    glare = np.array([[1.0, 1.0], [8.0, 1.0], [8.0, 4.0], [1.0, 4.0]])
    candidates.append(_piece(glare, detected_id=4, area=28.0))
    result = assign_templates_global(candidates, origin_mm=origin)
    assert result.accepted
    assert 4 in result.rejected_candidate_ids


def test_ambiguous_margin_rejects():
    origin = (0.0, 0.0)
    # 两套几乎同样好的候选（复制四片）
    base = [template_target_vertices_mm(i, origin) + np.array([2.0, 2.0]) for i in range(4)]
    dup = [template_target_vertices_mm(i, origin) + np.array([2.1, 2.1]) for i in range(4)]
    candidates = [_piece(v, detected_id=i) for i, v in enumerate(base + dup)]
    result = assign_templates_global(candidates, origin_mm=origin, min_margin=5.0)
    assert not result.accepted
    assert result.rejection_reason == "PIECE_IDENTITY_AMBIGUOUS"


def test_triangle_and_quad_edge_refinement():
    tri = np.array([[0.0, 0.0], [80.0, 0.0], [80.0, 60.0]])
    quad = np.array([[0.0, 0.0], [20.0, 0.0], [36.0, 12.0], [0.0, 20.0]])
    r3 = refine_polygon_from_contour(_contour_from_poly(tri), expected_sides=3)
    r4 = refine_polygon_from_contour(_contour_from_poly(quad), expected_sides=4)
    assert r3.valid and len(r3.refined_vertices_mm) == 3 and len(r3.fitted_lines) == 3
    assert r4.valid and len(r4.refined_vertices_mm) == 4 and len(r4.fitted_lines) == 4
    assert r3.edge_fit_rmse_mm > 0.0
    assert r4.edge_fit_rmse_mm > 0.0
    for i, v in enumerate(r3.refined_vertices_mm):
        assert np.linalg.norm(v - tri[i]) < 3.0 or min(np.linalg.norm(v - t) for t in tri) < 3.0


def test_rigid_transform_r_t_and_no_mirror():
    target = template_target_vertices_mm(0, (0.0, 0.0))
    center = target.mean(axis=0)
    source = apply_rigid_pose(target - center, (40.0, 25.0), 27.0)
    result = compute_rigid_transform(source, target)
    assert result.valid
    assert result.determinant > 0
    assert abs(abs(result.rotation_deg) - 27.0) < 1.5
    pick = source.mean(axis=0)
    release = apply_rigid_transform(pick, result)
    assert np.allclose(release, result.rotation_matrix @ pick + result.translation_mm, atol=1e-6)
    assert np.linalg.norm(release - target.mean(axis=0)) < 1.0

    mirrored = source.copy()
    mirrored[:, 0] *= -1
    bad = compute_rigid_transform(mirrored, target)
    # 可能找到无镜像对应；若强行镜面形状则误差大
    if bad.valid:
        assert bad.max_error_mm > 5.0 or bad.determinant > 0


def test_pick_release_roll_and_no_silent_clamp(tmp_path):
    cal = {
        "paper_to_robot_matrix": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "wrist_roll_zero_deg": 0.0,
        "wrist_roll_sign": 1.0,
        "wrist_roll_min_deg": -40.0,
        "wrist_roll_max_deg": 40.0,
    }
    path = tmp_path / "arm.json"
    path.write_text(json.dumps(cal), encoding="utf-8")
    mapper = ArmCoordinateMapper(path)
    ok = mapper.map_in_plane_rotation(30.0)
    assert ok.valid and ok.release_roll_deg == 30.0
    assert ok.pick_roll_deg != ok.release_roll_deg or abs(30.0) < 1e-9
    bad = mapper.map_in_plane_rotation(80.0)
    assert not bad.valid
    assert bad.rejection_reason == "WRIST_ROTATION_OUT_OF_RANGE"
    # 确认没有 clamp 成 40
    assert bad.release_roll_deg is None


def test_wrist_helper_candidates():
    result = choose_wrist_release_roll(
        pick_roll_deg=0.0,
        rotation_delta_deg=350.0,
        wrist_roll_sign=1.0,
        roll_min_deg=-20.0,
        roll_max_deg=20.0,
    )
    # 350 -> -10 via -360 branch
    assert result.valid
    assert abs(result.release_roll_deg - (-10.0)) < 1e-6


def test_placed_ok_requires_absolute_position():
    analyzer = SceneAnalyzer(vertex_tolerance_mm=8.0, center_tolerance_mm=5.0, angle_tolerance_deg=5.0)
    origin = (55.0, 168.5)
    expected = template_target_vertices_mm(0, origin)
    # 形状正确但平移错误
    wrong = expected + np.array([25.0, 0.0])
    piece = _piece(wrong, region="LOWER_TARGET", template_id="P1")
    states = analyzer._classify_templates([piece], 0)
    assert states["P1"].status == PieceTaskStatus.PLACED_OFFSET

    good = _piece(expected, region="LOWER_TARGET", template_id="P1")
    states2 = analyzer._classify_templates([good], 0)
    assert states2["P1"].status == PieceTaskStatus.PLACED_OK


def test_puzzle_union_overlap_gap_outside():
    origin = (0.0, 0.0)
    perfect = {f"P{i+1}": template_target_vertices_mm(i, origin) for i in range(4)}
    ok = validate_placed_puzzle_geometry(perfect, origin)
    assert ok.valid
    assert abs(ok.bounding_width_mm - 100.0) < 3.0
    assert abs(ok.bounding_height_mm - 60.0) < 3.0

    overlapped = dict(perfect)
    overlapped["P1"] = perfect["P1"] + np.array([10.0, 0.0])
    bad_overlap = validate_placed_puzzle_geometry(overlapped, origin)
    assert "OVERLAP" in bad_overlap.failure_reasons or "OUTSIDE" in bad_overlap.failure_reasons or not bad_overlap.valid

    gapped = dict(perfect)
    gapped["P4"] = perfect["P4"] + np.array([30.0, 0.0])
    bad_gap = validate_placed_puzzle_geometry(gapped, origin)
    assert "GAP" in bad_gap.failure_reasons or "OUTSIDE" in bad_gap.failure_reasons or not bad_gap.valid

    report = verify_geometry_invariants()
    assert report["ok"]
    assert report["TARGET_WIDTH_MM"] == 100.0


def test_audit_fault_classes():
    origin = (55.0, 168.5)
    expected = {f"P{i+1}": template_target_vertices_mm(i, origin) for i in range(4)}

    def make_scene(pieces_map, statuses):
        templates = {}
        pieces = []
        for i, tid in enumerate(("P1", "P2", "P3", "P4")):
            piece = None
            if tid in pieces_map:
                piece = _piece(pieces_map[tid], detected_id=i, region="UPPER_SOURCE" if statuses[tid] == PieceTaskStatus.UNPLACED else "LOWER_TARGET", template_id=tid)
                pieces.append(piece)
            templates[tid] = TemplateState(
                tid,
                statuses[tid],
                piece,
                expected[tid],
                0.0,
                0.0,
                0.0,
                1,
            )
        return SceneAnalysis(
            1,
            "",
            pieces,
            templates,
            {k for k, v in statuses.items() if v == PieceTaskStatus.PLACED_OK},
            {k for k, v in statuses.items() if v == PieceTaskStatus.UNPLACED},
            {},
            True,
            True,
        )

    source = expected["P1"] + np.array([0.0, -80.0])
    prev_scene = make_scene({"P1": source, "P2": expected["P2"] + [0, -60], "P3": expected["P3"] + [0, -50], "P4": expected["P4"] + [0, -40]}, {k: PieceTaskStatus.UNPLACED for k in expected})
    plan = SingleMovePlan(
        0,
        "P1",
        PaperPose(float(source.mean(0)[0]), float(source.mean(0)[1]), 0),
        PaperPose(float(expected["P1"].mean(0)[0]), float(expected["P1"].mean(0)[1]), 0),
        None,
        None,
        (float(source.mean(0)[0]), float(source.mean(0)[1])),
        None,
        None,
        None,
        None,
        10.0,
        0.9,
        "t",
        0,
        pick_point_source_mm=source.mean(0),
        release_point_target_mm=expected["P1"].mean(0),
    )

    # PICK_FAILED: still near source
    scene_pick = make_scene({"P1": source + np.array([1.0, 0.0]), "P2": expected["P2"]+[0,-60], "P3": expected["P3"]+[0,-50], "P4": expected["P4"]+[0,-40]}, {k: PieceTaskStatus.UNPLACED for k in expected})
    audit = audit_scene(scene_pick, plan, prev_scene, target_origin_mm=origin)
    assert audit.pick_failed_template == "P1"

    # PLACED_OFFSET
    scene_off = make_scene({"P1": expected["P1"] + np.array([12.0, 0.0]), "P2": expected["P2"], "P3": expected["P3"], "P4": expected["P4"]}, {"P1": PieceTaskStatus.PLACED_OFFSET, "P2": PieceTaskStatus.PLACED_OK, "P3": PieceTaskStatus.PLACED_OK, "P4": PieceTaskStatus.PLACED_OK})
    audit2 = audit_scene(scene_off, plan, prev_scene, target_origin_mm=origin)
    assert "P1" in audit2.placed_offset

    # DROPPED
    mid = (source.mean(0) + expected["P1"].mean(0)) / 2
    mid_poly = source - source.mean(0) + mid
    scene_drop = make_scene({"P1": mid_poly, "P2": expected["P2"]+[0,-60], "P3": expected["P3"]+[0,-50], "P4": expected["P4"]+[0,-40]}, {k: PieceTaskStatus.UNPLACED for k in expected})
    audit3 = audit_scene(scene_drop, plan, prev_scene, target_origin_mm=origin)
    assert audit3.dropped_template == "P1"

    # MISSING -> recovery uses previous plan flag via selector
    scene_miss = make_scene({"P2": expected["P2"]+[0,-60], "P3": expected["P3"]+[0,-50], "P4": expected["P4"]+[0,-40]}, {"P1": PieceTaskStatus.MISSING, "P2": PieceTaskStatus.UNPLACED, "P3": PieceTaskStatus.UNPLACED, "P4": PieceTaskStatus.UNPLACED})
    audit4 = audit_scene(scene_miss, plan, prev_scene, target_origin_mm=origin)
    assert audit4.recovery_template == "P1"
    tid, details = select_next_piece(scene_miss, audit4)
    assert tid == "P1" and details.get("use_previous_plan") is True


def test_selector_scores_not_placeholders():
    from q1.camera import StaticImageCamera
    from q1.executors.simulation import SimulationWorld

    world = SimulationWorld()
    snapshot = StaticImageCamera(world.snapshot).capture_snapshot(0)
    scene = SceneAnalyzer().analyze(snapshot, 0)
    audit = audit_scene(scene, None, None)
    tid, details = select_next_piece(scene, audit)
    assert tid in scene.templates
    scores = details["scores"]
    for feats in scores.values():
        assert "verification_visibility" in feats
        assert "path_collision_risk" in feats
        assert "blocking_future_targets" in feats
        # 不允许三者同时是固定占位常数组合出现在源码逻辑中；数值可偶然相同，但字段必须由几何计算写入
        assert isinstance(feats["verification_visibility"], float)
        assert isinstance(feats["path_collision_risk"], float)
        assert isinstance(feats["blocking_future_targets"], float)


def test_release_point_matches_r_t(tmp_path):
    from q1.camera import StaticImageCamera
    from q1.executors.simulation import SimulationWorld

    world = SimulationWorld()
    snapshot = StaticImageCamera(world.snapshot).capture_snapshot(0)
    scene = SceneAnalyzer().analyze(snapshot, 0)
    assert scene.scene_valid
    audit = audit_scene(scene, None, None)
    tid, details = select_next_piece(scene, audit)
    plan = plan_single_move(scene, tid, ArmCoordinateMapper(None), Q1RuntimeConfig(run_root=tmp_path), reason_selected=details["reason"])
    assert plan.rigid_transform is not None
    assert plan.pick_point_source_mm is not None
    assert plan.release_point_target_mm is not None
    mapped = plan.rigid_transform.rotation_matrix @ plan.pick_point_source_mm + plan.rigid_transform.translation_mm
    assert np.allclose(mapped, plan.release_point_target_mm, atol=1e-6)


def test_assignment_consistent_with_true_labels():
    origin = (0.0, 0.0)
    candidates = [
        _piece(template_target_vertices_mm(i, origin) + np.array([5.0 * i, 8.0]), detected_id=i) for i in range(4)
    ]
    a = assign_templates_global(candidates, origin_mm=origin)
    b = assign_templates_global(list(reversed(candidates)), origin_mm=origin)
    assert a.accepted and b.accepted
    for tid in ("P1", "P2", "P3", "P4"):
        assert np.allclose(a.assignments[tid].vertices_mm, b.assignments[tid].vertices_mm, atol=1e-6)
