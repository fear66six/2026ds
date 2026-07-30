"""电磁铁保持会话；真实驱动仅在显式 initialize 时打开。"""

from __future__ import annotations

import threading
import time
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

    def assert_healthy(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    @contextmanager
    def hold_session(self):
        self.start_hold()
        try:
            yield self
        except BaseException:
            try:
                self.emergency_off()
            except BaseException:
                pass
            raise
        else:
            self.stop_hold()


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
        self._io_lock = threading.Lock()
        self.events: list[dict] = []

    def _event(self, name: str, **details) -> None:
        self.events.append(
            {"event": name, "monotonic_s": time.monotonic(), **details}
        )

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
        try:
            self.client.open()
            with self._io_lock:
                self.client.magnet_off()
                if not self.client.ping():
                    raise RuntimeError("STM32 magnet PING failed")
                status = self.client.get_status()
            if status.magnet or status.fault:
                raise RuntimeError(f"unsafe STM32 magnet initial status: {status}")
        except BaseException:
            try:
                self.client.emergency_off()
            except BaseException:
                pass
            self.client.close()
            self.client = None
            raise
        self.is_holding = False
        self._event("INITIALIZED_OFF", port=self.port, status=str(status))

    def ensure_off(self) -> None:
        if self.client is not None:
            with self._io_lock:
                self.client.magnet_off()
                status = self.client.get_status()
            if status.magnet or status.fault:
                raise RuntimeError(f"STM32 magnet failed safe-off check: {status}")
        self.is_holding = False
        self._event("OFF_CONFIRMED")

    def _renew(self) -> None:
        assert self.client is not None and self.lease_ms is not None and self.renew_interval_ms is not None
        try:
            while not self._stop.wait(self.renew_interval_ms / 1000.0):
                with self._io_lock:
                    self.client.magnet_on(self.lease_ms)
                self._event("LEASE_RENEWED", lease_ms=self.lease_ms)
        except BaseException as exc:
            self._error = exc
            self._stop.set()
            self._event("LEASE_RENEW_FAILED", error=repr(exc))

    def start_hold(self) -> None:
        if self.client is None or self.lease_ms is None:
            raise RuntimeError("电磁铁驱动尚未初始化")
        if self.is_holding:
            raise RuntimeError("电磁铁保持会话已启动")
        self._error = None
        self._stop.clear()
        try:
            with self._io_lock:
                self.client.magnet_on(self.lease_ms)
                status = self.client.get_status()
            if not status.magnet or status.fault:
                raise RuntimeError(f"STM32 magnet did not enter safe ON state: {status}")
        except BaseException:
            try:
                with self._io_lock:
                    self.client.emergency_off()
            except BaseException:
                pass
            raise
        self.is_holding = True
        self._event("HOLD_START_CONFIRMED", lease_ms=self.lease_ms)
        self._thread = threading.Thread(target=self._renew, name="q1-magnet-renew", daemon=True)
        self._thread.start()

    def assert_healthy(self) -> None:
        if self._error is not None:
            raise RuntimeError("电磁铁续租失败") from self._error
        if not self.is_holding or self._thread is None or not self._thread.is_alive():
            raise RuntimeError("电磁铁保持线程未运行")

    def stop_hold(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        try:
            if self.client is not None:
                with self._io_lock:
                    self.client.magnet_off()
                    status = self.client.get_status()
                if status.magnet or status.fault:
                    raise RuntimeError(f"STM32 magnet OFF verification failed: {status}")
        finally:
            self.is_holding = False
        self._event("HOLD_STOP_CONFIRMED")
        if self._error is not None:
            error, self._error = self._error, None
            raise RuntimeError("电磁铁续租失败") from error

    def emergency_off(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        try:
            if self.client is not None:
                with self._io_lock:
                    self.client.emergency_off()
        finally:
            self.is_holding = False
            self._event("EMERGENCY_OFF_SENT")

    def close(self) -> None:
        try:
            self.emergency_off()
        finally:
            if self.client is not None:
                self.client.close()
                self.client = None
