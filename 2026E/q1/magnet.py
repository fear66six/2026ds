"""电磁铁保持会话；真实驱动仅在显式 initialize 时打开。"""

from __future__ import annotations

import threading
from contextlib import contextmanager


class MagnetControllerAdapter:
    def initialize(self) -> None:
        raise NotImplementedError

    def ensure_off(self) -> None:
        raise NotImplementedError

    def start_hold(self) -> None:
        raise NotImplementedError

    def stop_hold(self) -> None:
        raise NotImplementedError

    def emergency_off(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    @contextmanager
    def hold_session(self):
        self.start_hold()
        try:
            yield self
        except BaseException:
            self.emergency_off()
            raise
        finally:
            self.stop_hold()


class SimulationMagnetController(MagnetControllerAdapter):
    def __init__(self) -> None:
        self.is_holding = False
        self.events: list[str] = []

    def initialize(self) -> None:
        self.ensure_off()

    def ensure_off(self) -> None:
        self.is_holding = False
        self.events.append("OFF")

    def start_hold(self) -> None:
        self.is_holding = True
        self.events.append("HOLD_START")

    def stop_hold(self) -> None:
        self.is_holding = False
        self.events.append("HOLD_STOP")

    def emergency_off(self) -> None:
        self.is_holding = False
        self.events.append("EMERGENCY_OFF")

    def close(self) -> None:
        self.ensure_off()


class STM32MagnetController(MagnetControllerAdapter):
    """使用 drivers/stm32_magnet_uart.py 的 50–500ms 限时命令安全续租。"""

    def __init__(self, port: str, *, lease_ms: int | None = None) -> None:
        self.port = port
        self.lease_ms = lease_ms
        self.renew_interval_ms: int | None = None
        self.client = None
        self.is_holding = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._error: BaseException | None = None

    def initialize(self) -> None:
        from drivers.stm32_magnet_uart import (
            MAX_TIMEOUT_MS,
            MIN_TIMEOUT_MS,
            STM32MagnetUART,
            SerialTransport,
        )

        lease = MAX_TIMEOUT_MS if self.lease_ms is None else self.lease_ms
        if not MIN_TIMEOUT_MS <= lease <= MAX_TIMEOUT_MS:
            raise ValueError(f"续租时长必须在真实协议范围{MIN_TIMEOUT_MS}..{MAX_TIMEOUT_MS}ms")
        self.lease_ms = lease
        self.renew_interval_ms = lease // 2
        self.client = STM32MagnetUART(SerialTransport(port=self.port))
        self.client.open()
        self.ensure_off()

    def ensure_off(self) -> None:
        if self.client is not None:
            self.client.magnet_off()
        self.is_holding = False

    def _renew(self) -> None:
        assert self.client is not None and self.lease_ms is not None and self.renew_interval_ms is not None
        try:
            while not self._stop.wait(self.renew_interval_ms / 1000.0):
                self.client.magnet_on(self.lease_ms)
        except BaseException as exc:
            self._error = exc
            self._stop.set()

    def start_hold(self) -> None:
        if self.client is None or self.lease_ms is None:
            raise RuntimeError("电磁铁驱动尚未初始化")
        if self.is_holding:
            raise RuntimeError("电磁铁保持会话已启动")
        self._error = None
        self._stop.clear()
        self.client.magnet_on(self.lease_ms)
        self.is_holding = True
        self._thread = threading.Thread(target=self._renew, name="q1-magnet-renew", daemon=True)
        self._thread.start()

    def stop_hold(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        try:
            if self.client is not None:
                self.client.magnet_off()
        finally:
            self.is_holding = False
        if self._error is not None:
            error, self._error = self._error, None
            raise RuntimeError("电磁铁续租失败") from error

    def emergency_off(self) -> None:
        self._stop.set()
        if self.client is not None:
            self.client.emergency_off()
        self.is_holding = False

    def close(self) -> None:
        try:
            self.emergency_off()
        finally:
            if self.client is not None:
                self.client.close()
                self.client = None
