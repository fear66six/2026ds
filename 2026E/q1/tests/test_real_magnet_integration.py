from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from drivers import stm32_magnet_uart
from q1.executors.nexarm import NexArmRobotExecutor
from q1.magnet import STM32MagnetController
from q1.main import build_controller, parse_args
from q1.models import PaperPose, RobotPose, SingleMovePlan


def test_stm32_controller_handshake_on_and_verified_off(monkeypatch):
    transport = stm32_magnet_uart.MockTransport()
    monkeypatch.setattr(
        stm32_magnet_uart,
        "SerialTransport",
        lambda **_kwargs: transport,
    )
    magnet = STM32MagnetController("/dev/serial/by-id/test-stm32", lease_ms=500)
    magnet.initialize()
    assert transport.is_open
    assert not transport.magnet_on

    magnet.start_hold()
    assert transport.magnet_on
    magnet.assert_healthy()
    magnet.stop_hold()
    assert not transport.magnet_on
    assert [item["event"] for item in magnet.events] == [
        "INITIALIZED_OFF",
        "HOLD_START_CONFIRMED",
        "HOLD_STOP_CONFIRMED",
    ]
    magnet.close()
    assert not transport.is_open


def test_hold_exception_forces_emergency_off(monkeypatch):
    transport = stm32_magnet_uart.MockTransport()
    monkeypatch.setattr(
        stm32_magnet_uart,
        "SerialTransport",
        lambda **_kwargs: transport,
    )
    magnet = STM32MagnetController("/dev/serial/by-id/test-stm32", lease_ms=500)
    magnet.initialize()
    with pytest.raises(RuntimeError, match="transfer failed"):
        with magnet.hold_session():
            assert transport.magnet_on
            raise RuntimeError("transfer failed")
    assert not transport.magnet_on
    assert not magnet.is_holding
    magnet.close()


def test_stm32_backend_uses_configured_port_without_cli_override():
    args = parse_args(
        [
            "--robot-config",
            "q1/config/robot_config.json",
            "--magnet-backend",
            "stm32",
            "--confirm",
            "RUN_Q1",
        ]
    )
    controller = build_controller(args)
    assert isinstance(controller.magnet, STM32MagnetController)
    assert controller.magnet.port.endswith("5B7A030191-if00")
    assert controller.magnet.lease_ms == 500


def test_sim_backend_is_not_a_valid_production_argument():
    with pytest.raises(SystemExit):
        parse_args(["--magnet-backend", "sim"])


def test_failed_hold_health_blocks_release_pose_before_send():
    config = SimpleNamespace(
        magnet_settle_ms=0,
        magnet_release_settle_ms=0,
        magnet_backend="stm32",
    )
    executor = NexArmRobotExecutor(Path("."), config)
    sent: list[str] = []
    source = RobotPose(246, 35, 25, -84.4, 0, 0, 6000)
    release = RobotPose(273, -50, 25, -84.4, 0, 0, 6000)
    plan = SingleMovePlan(
        0,
        "P3",
        PaperPose(1, 1),
        PaperPose(2, 2),
        source,
        release,
        (1, 1),
        source,
        source,
        release,
        release,
        0,
        1,
        "test",
        0,
    )
    executor._move_and_wait = lambda pose: sent.append(
        "source" if pose is source else "release"
    )

    class FailedMagnet:
        events = []

        @contextmanager
        def hold_session(self):
            yield self

        def assert_healthy(self):
            raise RuntimeError("lease failed")

    with pytest.raises(RuntimeError, match="lease failed"):
        executor.execute_single_move(plan, FailedMagnet())
    assert sent == ["source"]
