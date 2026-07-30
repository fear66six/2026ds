from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import q1.executors.nexarm as nexarm_module
import q1.motion as motion_module
from q1.calibration import ArmCoordinateMapper
from q1.config import DIVIDER_Y_CM
from q1.controller import Q1Controller, RunRecorder
from q1.executors.nexarm import NexArmRobotExecutor
from q1.geometry import compute_rigid_transform
from q1.main import build_controller, parse_args
from q1.models import ExecutionResult, RobotPose, SingleMovePlan, PaperPose
from q1.motion import plan_single_move
from q1.pieces import template_target_vertices_mm
from q1.runtime_config import Q1RuntimeConfig
from q1.vision import PaperFrame, detect_divider_line


Q1_ROOT = Path(__file__).resolve().parents[1]
ROBOT_CONFIG = Q1_ROOT / "config" / "robot_config.json"


def configured_runtime(**overrides) -> Q1RuntimeConfig:
    robot = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    overrides.setdefault("magnet_port", robot["magnet_port"])
    config = Q1RuntimeConfig(
        robot_config=ROBOT_CONFIG,
        nexarm_port=robot["nexarm_port"],
        **overrides,
    )
    for key in (
        "pick_height",
        "release_height",
        "move_duration_ms",
        "magnet_settle_ms",
        "magnet_release_settle_ms",
        "magnet_lease_ms",
        "position_tolerance_mm",
        "orientation_tolerance_deg",
        "motion_timeout_s",
        "vertex_max_error_mm",
    ):
        setattr(config, key, robot[key])
    config.motion_mode = robot["motion_mode"]
    config.direct_pick_release_pose_verified = robot[
        "direct_pick_release_pose_verified"
    ]
    config.motion_calibration_status = robot["motion_calibration_status"]
    config.physical_pick_verified = robot["physical_pick_verified"]
    config.idle_stable_samples = robot["stable_samples"]
    return config


def test_paper_to_robot_four_corners_and_center():
    mapper = ArmCoordinateMapper(ROBOT_CONFIG)
    expected = {
        (0.0, 0.0): (173.0, 145.0),
        (210.0, 0.0): (373.0, 145.0),
        (0.0, 297.0): (173.0, -145.0),
        (210.0, 297.0): (373.0, -145.0),
        (105.0, 148.5): (273.0, 0.0),
    }
    for paper, robot in expected.items():
        pose = mapper.paper_to_robot(*paper, 100.0)
        assert (pose.x, pose.y) == pytest.approx(robot)


def test_landscape_paper_uses_known_halfway_divider():
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    paper = PaperFrame(
        corners_px=np.array(
            [[200, 10], [1120, 10], [1120, 690], [200, 690]], dtype=np.float32
        ),
        px_per_cm=32.0,
        landscape_in_image=True,
    )
    assert detect_divider_line(frame, paper) == pytest.approx(DIVIDER_Y_CM)


def test_wrist_sign_mapping_has_no_software_range_limit():
    mapper = ArmCoordinateMapper(ROBOT_CONFIG)
    assert mapper.map_in_plane_rotation(0).release_roll_deg == pytest.approx(0)
    assert mapper.map_in_plane_rotation(30).release_roll_deg == pytest.approx(30)
    assert mapper.map_in_plane_rotation(-30).release_roll_deg == pytest.approx(-30)
    assert mapper.map_in_plane_rotation(30, pick_roll_deg=720).release_roll_deg == 750


def test_sim_is_rejected_and_stm32_requires_port():
    sim = configured_runtime(magnet_backend="sim", magnet_port=None)
    assert any("REAL_STM32_MAGNET_REQUIRED" in item for item in sim.real_run_blockers())
    real = configured_runtime(magnet_backend="stm32", magnet_port=None)
    assert any("MAGNET_PORT_REQUIRED" in item for item in real.real_run_blockers())


def test_only_single_full_q1_confirmation_is_accepted():
    args = parse_args(
        [
            "--robot-config",
            str(ROBOT_CONFIG),
        ]
    )
    with pytest.raises(RuntimeError, match="CONFIRMATION_REQUIRED"):
        build_controller(args)
    assert not hasattr(args, "paper_calibration")
    assert not hasattr(args, "arm_calibration")
    assert not hasattr(args, "safety_config")
    assert not hasattr(args, "nexarm_port")


def test_robot_parameters_are_consolidated_and_direct_pose_is_required():
    robot = json.loads(ROBOT_CONFIG.read_text(encoding="utf-8"))
    required = {
        "nexarm_port",
        "home_pose",
        "paper_to_robot_matrix",
        "wrist_roll_zero_deg",
        "motion_mode",
        "pick_height",
        "release_height",
        "move_duration_ms",
        "position_tolerance_mm",
    }
    assert required <= robot.keys()
    assert robot["position_tolerance_mm"] == 10.0
    assert robot["motion_mode"] == "direct_pose"
    assert robot["direct_pick_release_pose_verified"] is True
    assert robot["physical_pick_verified"] is False
    assert robot["home_pose"] == [175.0, 0.0, 210.0, -90.0, 0.0, 0.0]
    assert robot["pick_height"] == 15.0
    assert robot["release_height"] == 15.0
    assert "workspace_limits" not in robot
    assert "wrist_roll_min_deg" not in robot
    assert "wrist_roll_max_deg" not in robot
    assert "single_pose_calibration" not in robot
    assert robot["magnet_port"].endswith("5B7A030191-if00")
    assert "safe_height" not in robot
    assert "release_peel_delta" not in robot
    assert "global_acceleration" not in robot


def test_planning_residual_over_limit_blocks_before_robot_pose(monkeypatch):
    piece = SimpleNamespace(
        region="UPPER_SOURCE",
        center_mm=(50.0, 50.0),
        vertices_mm=np.array([[0.0, 0.0], [30.0, 0.0], [0.0, 20.0]]),
        angle_deg=0.0,
        confidence=0.9,
    )
    scene = SimpleNamespace(
        cycle_index=0,
        templates={
            "P3": SimpleNamespace(
                detected_piece=piece,
                expected_target_vertices_mm=np.array(
                    [[50.0, 180.0], [80.0, 180.0], [50.0, 200.0]]
                ),
                retry_count=0,
            )
        },
    )
    monkeypatch.setattr(
        motion_module,
        "compute_rigid_transform",
        lambda *_args, **_kwargs: SimpleNamespace(
            valid=True,
            rejection_reason=None,
            max_error_mm=18.34,
            rms_error_mm=14.83,
        ),
    )
    with pytest.raises(RuntimeError, match="PLAN_GEOMETRY_RESIDUAL"):
        plan_single_move(
            scene,
            "P3",
            ArmCoordinateMapper(None),
            configured_runtime(),
            reason_selected="test",
        )


def test_current_solid_piece_layout_uses_global_mirror_not_piece_reflection():
    # Run 20260729_143453_743075 P3: the physical four-piece set has the
    # opposite chirality to the figure-coordinate template. Mirroring the
    # complete target layout makes a rotation-only placement possible.
    detected_p3 = np.array(
        [
            [28.12502923299798, 137.80792912881196],
            [128.62515703688587, 123.24203503214176],
            [123.95781594107093, 91.09509103610577],
            [47.281430622044695, 117.01689602396328],
        ]
    )
    target = template_target_vertices_mm(2, (55.0, 168.5))
    transform = compute_rigid_transform(detected_p3, target)
    assert transform.determinant > 0.0
    assert not transform.mirrored
    assert transform.max_error_mm == pytest.approx(2.2648, abs=0.01)


def test_initialize_handshakes_without_pre_home_controller_write(tmp_path):
    sdk = tmp_path / "hardware" / "nexarm" / "jetson_to_nexarm" / "nexarm_sdk.py"
    sdk.parent.mkdir(parents=True)
    sdk.write_text(
        """
from types import SimpleNamespace
import time
class NexArmClient:
    def __init__(self, port):
        self.port = port
        self.write_commands = []
        self.last_rx_diagnostics = {}
    def open(self): pass
    def close(self): pass
    def flush_input_buffer(self): return 0
    def get_firmware_version(self, timeout): return "1.0.0"
    def get_current_coords(self, timeout):
        now = time.monotonic()
        return SimpleNamespace(
            x=173, y=4, z=226, pitch=-84.4, roll=0, claw=0,
            servo_positions=(1,2,3,4,5,6),
            meta={
                "bytes_discarded": 0,
                "request_started_s": now,
                "response_received_s": now,
                "skipped_packets": 0,
            },
        )
    def set_global_acceleration(self, value):
        self.write_commands.append(("set_global_acceleration", value))
""",
        encoding="utf-8",
    )
    executor = NexArmRobotExecutor(tmp_path, configured_runtime())
    executor.initialize()
    assert executor.client.write_commands == []
    assert executor._initial_status["firmware_version"] == "1.0.0"
    assert executor._initial_status["initial_pose"] == [
        173.0,
        4.0,
        226.0,
        -84.4,
        0.0,
        0.0,
    ]
    assert "global_acceleration" not in executor._initial_status


def test_move_sequence_does_not_finish_before_command_duration(monkeypatch):
    config = configured_runtime()
    executor = NexArmRobotExecutor(Q1_ROOT.parent, config)
    target = np.array([173.0, 4.0, 226.0, -84.4, 0.0, 0.0])
    clock = [0.0]

    class FakeClient:
        def set_pose(self, *_values):
            return None

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    executor._move_and_wait(RobotPose(*target.tolist(), 6000))
    assert clock[0] >= 6.0
    assert executor._active_motion_attempt["result"] == "DURATION_ELAPSED"


def test_executor_sends_only_direct_pick_and_release_targets():
    config = configured_runtime()
    executor = NexArmRobotExecutor(Q1_ROOT.parent, config)
    visited: list[float] = []
    executor._move_and_wait = lambda pose: visited.append(pose.x)
    executor._last_actual = np.array([10.0, 20.0, 226.0, -84.4, 0.0, 0.0])
    approach = RobotPose(1, 0, 226, -84.4, 0, 0, 6000)
    source = RobotPose(2, 0, 25, -84.4, 0, 0, 6000)
    rotate = RobotPose(3, 0, 226, -84.4, 10, 0, 6000)
    transfer = RobotPose(4, 0, 226, -84.4, 10, 0, 6000)
    release = RobotPose(5, 0, 25, -84.4, 10, 0, 6000)
    plan = SingleMovePlan(
        0, "P1", PaperPose(1, 1), PaperPose(2, 2), source, release,
        (1, 1), source, approach, transfer, release, 10, 1, "test", 0,
        rotate_pose=rotate,
    )

    class FakeMagnet:
        events = []

        def assert_healthy(self):
            return None

        def hold_session(self):
            class Session:
                def __enter__(self): return self
                def __exit__(self, *_args): return False
            return Session()

    result = executor.execute_single_move(plan, FakeMagnet())
    assert result.ok
    assert visited == [2, 5]
    assert result.details["trajectory_steps"] == [
        "direct_home_to_pick_pose_duration_elapsed",
        "direct_pick_to_release_pose_duration_elapsed",
        "magnet_off_after_release_pose_duration",
    ]
    assert "real_arm_motion" not in result.details
    assert result.details["physical_evidence"] == "UNPROVEN"


def test_run_report_announces_copyable_paths_and_latest_pointer(tmp_path, capsys):
    config = configured_runtime(
        authorization="RUN_Q1",
        mode="full_q1",
        magnet_backend="stm32",
    )
    recorder = RunRecorder(tmp_path, config.mode, config)
    payload = json.loads((recorder.directory / "run.json").read_text(encoding="utf-8"))
    output = capsys.readouterr().out
    assert f"Q1_RUN_ID={recorder.run_id}" in output
    assert f"Q1_RUN_DIR={recorder.directory}" in output
    assert f"Q1_RUN_EVENTS={recorder.events_path}" in output
    assert (tmp_path / "LATEST_RUN.txt").read_text(encoding="utf-8").strip() == str(
        recorder.directory
    )
    assert payload["authorization"] == "RUN_Q1"
    assert payload["magnet_backend"] == "stm32"
    assert payload["physical_pick_enabled"] is True
    assert payload["physical_pick_verified"] is False
    assert "USER_VERIFIED_Z15_2026-07-30" in payload["motion_calibration_status"]


def test_unverified_direct_pick_release_blocks_before_hardware_open():
    config = configured_runtime()
    config.direct_pick_release_pose_verified = False
    assert config.direct_pick_release_pose_verified is False
    assert "DIRECT_PICK_RELEASE_POSE_UNVERIFIED" in config.production_run_blockers()


def test_current_production_config_passes_direct_pose_verification_gate():
    args = parse_args(
        [
            "--robot-config",
            str(ROBOT_CONFIG),
            "--confirm",
            "RUN_Q1",
        ]
    )
    controller = build_controller(args)
    assert controller.config.direct_pick_release_pose_verified is True
    assert (
        "DIRECT_PICK_RELEASE_POSE_UNVERIFIED"
        not in controller.config.production_run_blockers()
    )
