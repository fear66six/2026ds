from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import q1.executors.nexarm as nexarm_module
from q1.executors.nexarm import NexArmRobotExecutor
from q1.models import PaperPose, RobotPose, SingleMovePlan
from q1.tests.test_q1_master_integration import Q1_ROOT, configured_runtime


def _meta(clock: list[float], discarded: int = 0) -> dict:
    started = clock[0]
    return {
        "bytes_discarded": discarded,
        "request_started_s": started,
        "response_received_s": started + 0.01,
        "skipped_packets": 0,
        "latency_s": 0.01,
    }


def test_static_feedback_does_not_block_duration_sequence(monkeypatch):
    config = configured_runtime()
    executor = NexArmRobotExecutor(Q1_ROOT.parent, config)
    start = np.array([168.0, 5.0, 219.0, -86.9, 0.0, 0.0])
    target = RobotPose(246.0, 35.0, 25.0, -84.4, 0.0, 0.0, 6000)
    clock = [0.0]

    class FakeClient:
        def __init__(self):
            self.flushes = 0

        def flush_input_buffer(self):
            self.flushes += 1
            return 3

        def set_pose(self, *values):
            return None

        def get_current_coords(self, timeout):
            return SimpleNamespace(
                x=start[0],
                y=start[1],
                z=start[2],
                pitch=start[3],
                roll=start[4],
                claw=start[5],
                servo_positions=(2028, 2108, 2038, 3087, 2048, 2048),
                meta=_meta(clock, discarded=3),
            )

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    executor._last_actual = start.copy()

    executor._move_and_wait(target)

    attempt = executor._motion_attempts[-1]
    assert attempt["result"] == "DURATION_ELAPSED"
    assert attempt["telemetry_outcome"] == "NOT_USED_FOR_SEQUENCE_CONTROL"
    assert attempt["physical_evidence"] == "UNPROVEN"
    assert executor.client.flushes == 0
    assert clock[0] >= 6.0


def test_duration_sequence_does_not_poll_post_command_feedback(monkeypatch):
    config = configured_runtime()
    executor = NexArmRobotExecutor(Q1_ROOT.parent, config)
    start = np.array([168.0, 5.0, 219.0, -86.9, 0.0, 0.0])
    goal = np.array([246.0, 35.0, 25.0, -84.4, 0.0, 0.0])
    target = RobotPose(*goal.tolist(), 6000)
    clock = [0.0]
    state = {"phase": "start"}

    class FakeClient:
        def flush_input_buffer(self):
            return 0

        def set_pose(self, *values):
            state["phase"] = "moving"

        def get_current_coords(self, timeout):
            pose = start if state["phase"] == "start" or clock[0] < 6.0 else goal
            servos = (
                (2028, 2108, 2038, 3087, 2048, 2048)
                if pose is start
                else (1900, 2200, 1800, 3000, 2048, 2048)
            )
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

    monkeypatch.setattr(nexarm_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        nexarm_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    executor.client = FakeClient()
    executor._last_actual = start.copy()
    executor._move_and_wait(target)
    assert executor._active_motion_attempt["result"] == "DURATION_ELAPSED"
    assert clock[0] >= 6.0


def test_magnet_starts_after_pick_duration(monkeypatch):
    config = configured_runtime()
    executor = NexArmRobotExecutor(Q1_ROOT.parent, config)
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
        source,
        source,
        release,
        10,
        1,
        "test",
        0,
        rotate_pose=source,
    )
    result = executor.execute_single_move(plan, FakeMagnet())
    assert result.ok
    assert order == [
        "move:2",
        "magnet_session_enter",
        "magnet_on",
        "magnet_healthy",
        "move:2",
        "magnet_healthy",
        "move:5",
        "magnet_healthy",
        "magnet_off",
    ]
    assert result.details["physical_evidence"] == "UNPROVEN"
    assert "real_arm_motion" not in result.details
