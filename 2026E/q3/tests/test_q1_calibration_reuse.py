from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from q1.calibration import ArmCoordinateMapper
from q1.main import _apply_robot_fields
from q3.runtime_config import Q3RuntimeConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROBOT_CONFIG = PROJECT_ROOT / "q1" / "config" / "robot_config.json"


def configured_q3_runtime() -> Q3RuntimeConfig:
    data = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    config = Q3RuntimeConfig(robot_config=ROBOT_CONFIG)
    _apply_robot_fields(config, data)
    return config


def _expected_z(data: dict, x_mm: float, y_mm: float, height: float) -> float:
    a, b, c = data["surface_z_plane_mm"]
    ref_x, ref_y = data["surface_z_ref_paper_mm"]
    plane = a * x_mm + b * y_mm + c
    ref_plane = a * ref_x + b * ref_y + c
    return float(height) + (plane - ref_plane)


def test_q3_loads_latest_q1_contact_plane_and_heights():
    data = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    config = configured_q3_runtime()
    mapper = ArmCoordinateMapper(config.robot_config)

    assert "surface_z_plane_mm" in data
    assert "surface_z_ref_paper_mm" in data
    assert config.pick_height == data["pick_height"]
    assert config.release_height == data["release_height"]
    assert config.pick_robot_xy_offset_mm == tuple(data["pick_robot_xy_offset_mm"])

    a, b, c = data["surface_z_plane_mm"]
    assert mapper.surface_z_mm(0.0, 0.0) == pytest.approx(c)
    assert mapper.surface_z_mm(210.0, 0.0) == pytest.approx(a * 210.0 + c)
    assert mapper.surface_z_mm(0.0, 297.0) == pytest.approx(b * 297.0 + c)

    # Shared XY matrix from e7e1a290 / 2febb608 corner refit.
    center = mapper.paper_to_robot(105.0, 148.5, 0.0)
    assert (center.x, center.y) == pytest.approx((240.0, 8.5), abs=1e-6)


def test_q3_shared_mapper_applies_point_specific_z_like_motion():
    """Mirror q3.motion._build_move Z path without importing shapely card_solver."""

    data = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    config = configured_q3_runtime()
    mapper = ArmCoordinateMapper(config.robot_config)

    pick_xy = (40.0, 40.0)  # upper/source half
    release_xy = (40.0, 210.0)  # lower/target half
    pick = mapper.paper_to_robot(*pick_xy, float(config.pick_height))
    release = mapper.paper_to_robot(*release_xy, float(config.release_height))

    assert pick.z == pytest.approx(
        _expected_z(data, *pick_xy, float(config.pick_height)), abs=1e-6
    )
    assert release.z == pytest.approx(
        _expected_z(data, *release_xy, float(config.release_height)), abs=1e-6
    )
    assert pick.z != pytest.approx(config.pick_height)
    assert release.z != pytest.approx(config.release_height)
    assert pick.z != pytest.approx(release.z)


def test_q3_move_planning_applies_q1_point_specific_z_compensation():
    pytest.importorskip("shapely")
    from q3.motion import _build_move

    data = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    config = configured_q3_runtime()
    mapper = ArmCoordinateMapper(config.robot_config)
    source_vertices = np.array(
        [[20.0, 20.0], [60.0, 20.0], [20.0, 60.0]],
        dtype=np.float64,
    )
    target_vertices = source_vertices + np.array([0.0, 170.0])

    move = _build_move(
        cycle_index=0,
        piece_id=0,
        source_vertices_mm=source_vertices,
        target_vertices_mm=target_vertices,
        mapper=mapper,
        config=config,
        confidence=1.0,
    )

    expected_pick_z = _expected_z(
        data,
        float(move.pick_point_source_mm[0]),
        float(move.pick_point_source_mm[1]),
        float(config.pick_height),
    )
    expected_release_z = _expected_z(
        data,
        float(move.release_point_target_mm[0]),
        float(move.release_point_target_mm[1]),
        float(config.pick_height),
    )
    assert move.source_pose_robot.z == pytest.approx(expected_pick_z, abs=1e-6)
    assert move.target_pose_robot.z == pytest.approx(expected_release_z, abs=1e-6)
