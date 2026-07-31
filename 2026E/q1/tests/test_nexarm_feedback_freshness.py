from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

import q1.executors.nexarm as nexarm_module
from q1.executors.nexarm import NexArmRobotExecutor
from q1.models import PaperPose, RobotPose, SingleMovePlan
from q1.tests.test_q1_master_integration import configured_runtime


TARGET_SERVOS = (1900, 2200, 1800, 3000, 2048, 2048)


def _meta(clock: list[float], discarded: int = 0) -> dict:
    started = clock[0]
    return {
        "bytes_discarded": discarded,
        "request_started_s": started,
        "response_received_s": started + 0.01,
        "skipped_packets": 0,
        "latency_s": 0.01,
    }


def _coords(pose, servos, clock):
    return SimpleNamespace(
        x=float(pose[0]),
        y=float(pose[1]),
        z=float(pose[2]),
        pitch=float(pose[3]),
        roll=float(pose[4]),
        claw=float(pose[5]),
        servo_positions=servos,
        meta=_meta(clock),
    )


def test_servo_arrival_unblocks_after_stable_target_match(monkeypatch):
    config = configured_runtime()
    config.idle_stable_samples = 3
    config.motion_timeout_s = 12.0
    executor = NexArmRobotExecutor(
        __import__("pathlib").Path(__file__).resolve().parents[2], config
    )
    goal = np.array([246.0, 35.0, 25.0, -84.4, 0.0, 0.0])
    target = RobotPose(*goal.tolist(), 6000)
    clock = [0.0]

    class FakeClient:
        def set_pose(self, *values):
            return None

        def get_ikine_servo_positions(self, *values, timeout=0.5):
            return TARGET_SERVOS

        def get_current_coords(self, timeout):
            return _coords(goal, TARGET_SERVOS, clock)

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    executor._move_and_wait(target)
    attempt = executor._motion_attempts[-1]
    assert attempt["result"] == "TARGET_REACHED"
    assert attempt["telemetry_outcome"] == "ARRIVED"
    assert attempt["physical_evidence"] == "TARGET_SERVOS_WITHIN_TOLERANCE"
    assert clock[0] < 6.0


def test_ikine_timeout_fails_instead_of_hanging(monkeypatch):
    config = configured_runtime()
    config.motion_timeout_s = 1.0
    executor = NexArmRobotExecutor(
        __import__("pathlib").Path(__file__).resolve().parents[2], config
    )
    target = RobotPose(246.0, 35.0, 25.0, -84.4, 0.0, 0.0, 1000)
    clock = [0.0]

    class FakeClient:
        def set_pose(self, *values):
            return None

        def get_ikine_servo_positions(self, *values, timeout=0.5):
            raise TimeoutError("no ikine reply")

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    with pytest.raises(TimeoutError, match="MOTION_IKINE_TIMEOUT"):
        executor._move_and_wait(target)
    assert clock[0] >= 2.0


def test_arrival_timeout_fails_when_servos_never_match(monkeypatch):
    config = configured_runtime()
    config.motion_timeout_s = 1.0
    config.idle_stable_samples = 3
    executor = NexArmRobotExecutor(
        __import__("pathlib").Path(__file__).resolve().parents[2], config
    )
    goal = np.array([246.0, 35.0, 25.0, -84.4, 0.0, 0.0])
    target = RobotPose(*goal.tolist(), 1000)
    clock = [0.0]
    wrong = (100, 100, 100, 100, 100, 100)

    class FakeClient:
        def set_pose(self, *values):
            return None

        def get_ikine_servo_positions(self, *values, timeout=0.5):
            return TARGET_SERVOS

        def get_current_coords(self, timeout):
            return _coords(goal, wrong, clock)

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    with pytest.raises(TimeoutError, match="MOTION_ARRIVAL_TIMEOUT"):
        executor._move_and_wait(target)
    assert executor._active_motion_attempt["result"] == "ARRIVAL_TIMEOUT"


def test_magnet_starts_after_pick_arrival(monkeypatch):
    config = configured_runtime()
    executor = NexArmRobotExecutor(
        __import__("pathlib").Path(__file__).resolve().parents[2], config
    )
    order: list[str] = []

    def fake_move_and_wait(pose):
        order.append(f"move:{int(pose.x)}")

    class FakeMagnet:
        events: list[str] = []

        def hold_session(self):
            order.append("magnet_session_enter")

            class Session:
                def __enter__(self_inner):
                    order.append("magnet_on")
                    return self_inner

                def __exit__(self_inner, *_args):
                    order.append("magnet_off")
                    return False

            return Session()

        def assert_healthy(self):
            order.append("magnet_healthy")

    executor._move_and_wait = fake_move_and_wait
    monkeypatch.setattr(nexarm_module.time, "sleep", lambda _seconds: None)
    source = RobotPose(2, 0, 25, -84.4, 0, 0, 6000)
    transfer = RobotPose(4, 0, 80, -90, 0, 0, 3000)
    release = RobotPose(5, 0, 25, -84.4, 10, 0, 6000)
    plan = SingleMovePlan(
        0,
        "P1",
        PaperPose(1, 1),
        PaperPose(2, 2),
        source,
        release,
        (1, 1),
        source,
        None,
        transfer,
        release,
        10,
        1,
        "test",
        0,
        rotate_pose=None,
    )
    result = executor.execute_single_move(plan, FakeMagnet())
    assert result.ok
    assert order == [
        "move:2",
        "magnet_session_enter",
        "magnet_on",
        "magnet_healthy",
        "move:4",
        "magnet_healthy",
        "move:5",
        "magnet_healthy",
        "magnet_off",
    ]
    assert result.details["trajectory_steps"] == [
        "pick_pose_reached",
        "buffer_then_release_pose_reached",
        "magnet_off_after_release_pose_reached",
    ]
