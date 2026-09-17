from __future__ import annotations

from pathlib import Path

import pytest

import q1.executors.nexarm as nexarm_module
from q1.executors.nexarm import NexArmRobotExecutor
from q1.models import PaperPose, RobotPose, SingleMovePlan
from q1.tests.test_q1_master_integration import configured_runtime


def test_duration_and_settle_controls_progress_without_feedback(monkeypatch):
    config = configured_runtime()
    config.post_move_settle_ms = 200
    executor = NexArmRobotExecutor(Path(__file__).resolve().parents[2], config)
    target = RobotPose(246.0, 35.0, 25.0, -84.4, 0.0, 0.0, 1000)
    clock = [0.0]

    class FakeClient:
        def set_pose(self, *values):
            return None

        def get_ikine_servo_positions(self, *values, timeout=0.5):
            raise AssertionError("IK feedback must not control this sequence")

        def get_current_coords(self, timeout=0.5):
            raise AssertionError("pose feedback must not control this sequence")

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    executor._move_and_wait(target)

    attempt = executor._motion_attempts[-1]
    assert attempt["result"] == "DURATION_AND_SETTLE_ELAPSED"
    assert attempt["telemetry_outcome"] == "NOT_USED_FOR_SEQUENCE_CONTROL"
    assert attempt["physical_evidence"] == "UNPROVEN"
    assert attempt["elapsed_s"] == pytest.approx(1.2)
    assert clock[0] == pytest.approx(1.2)


def test_zero_settle_waits_only_for_controller_duration(monkeypatch):
    config = configured_runtime()
    config.post_move_settle_ms = 0
    executor = NexArmRobotExecutor(Path(__file__).resolve().parents[2], config)
    target = RobotPose(246.0, 35.0, 25.0, -84.4, 0.0, 0.0, 800)
    clock = [0.0]

    class FakeClient:
        def set_pose(self, *values):
            return None

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    executor._move_and_wait(target)

    assert clock[0] == pytest.approx(0.8)
    assert executor._motion_attempts[-1]["post_move_settle_s"] == 0.0


def test_magnet_starts_after_pick_descent_and_stays_on_through_transfer(monkeypatch):
    config = configured_runtime()
    executor = NexArmRobotExecutor(Path(__file__).resolve().parents[2], config)
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
    pick = RobotPose(2, 0, 25, -84.4, 0, 0, 800)
    pick_ready = RobotPose(1, 0, 65, -84.4, 0, 0, 1500)
    rotate = RobotPose(3, 0, 120, -84.4, 10, 0, 1200)
    transit = RobotPose(4, 0, 120, -84.4, 10, 0, 1500)
    release = RobotPose(5, 0, 25, -84.4, 10, 0, 800)
    plan = SingleMovePlan(
        0,
        "P1",
        PaperPose(1, 1),
        PaperPose(2, 2),
        pick,
        release,
        (1, 1),
        pick,
        pick_ready,
        transit,
        release,
        10,
        1,
        "test",
        0,
        rotate_pose=rotate,
    )

    result = executor.execute_single_move(plan, FakeMagnet())

    assert result.ok
    assert order == [
        "move:1",
        "move:2",
        "magnet_session_enter",
        "magnet_on",
        "magnet_healthy",
        "move:2",
        "move:3",
        "magnet_healthy",
        "move:4",
        "move:5",
        "move:5",
        "magnet_healthy",
        "magnet_off",
        "move:5",
    ]
    assert result.details["trajectory_steps"] == [
        "MOVE_TO_PICK_READY",
        "DESCEND_PICK",
        "LIFT_PICK",
        "ROTATE_IN_AIR",
        "TRANSIT_TO_PLACE",
        "MOVE_TO_PLACE_READY",
        "DESCEND_PLACE",
        "DONE_LIFT",
    ]
