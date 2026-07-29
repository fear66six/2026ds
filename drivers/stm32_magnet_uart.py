"""Safe USART1 client for the STM32 magnet controller.

Importing this module and constructing STM32MagnetUART never opens hardware.
Call open() explicitly. MockTransport supports offline tests without pyserial.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol


MIN_TIMEOUT_MS = 50
MAX_TIMEOUT_MS = 500


class Transport(Protocol):
    def open(self) -> None: ...
    def write_line(self, line: str) -> None: ...
    def read_line(self) -> str: ...
    def close(self) -> None: ...


class SerialTransport:
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial = None

    def open(self) -> None:
        import serial

        self._serial = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            write_timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )

    def write_line(self, line: str) -> None:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        self._serial.write((line + "\n").encode("ascii"))
        self._serial.flush()

    def read_line(self) -> str:
        if self._serial is None:
            raise RuntimeError("transport is not open")
        raw = self._serial.readline()
        if not raw.endswith(b"\n"):
            raise TimeoutError("no complete response line")
        return raw.decode("ascii", errors="strict").rstrip("\r\n")

    def close(self) -> None:
        if self._serial is not None:
            self._serial.close()
            self._serial = None


class MockTransport:
    def __init__(self):
        self.is_open = False
        self.magnet_on = False
        self._response = ""

    def open(self) -> None:
        self.is_open = True

    def write_line(self, line: str) -> None:
        if not self.is_open:
            raise RuntimeError("transport is not open")
        if line == "PING":
            self._response = "PONG"
        elif line == "GET_STATUS":
            self._response = f"STATUS MAGNET={int(self.magnet_on)} FAULT=0"
        elif line in {"MAGNET_OFF", "EMERGENCY_OFF"}:
            self.magnet_on = False
            self._response = "OK OFF"
        elif line.startswith("MAGNET_ON "):
            value = int(line.split(" ", 1)[1])
            if not MIN_TIMEOUT_MS <= value <= MAX_TIMEOUT_MS:
                self._response = "ERR invalid_timeout"
            else:
                self.magnet_on = True
                self._response = f"OK ON TIMEOUT_MS={value}"
        else:
            self.magnet_on = False
            self._response = "ERR unknown_command"

    def read_line(self) -> str:
        if not self.is_open:
            raise RuntimeError("transport is not open")
        return self._response

    def close(self) -> None:
        self.magnet_on = False
        self.is_open = False


@dataclass(frozen=True)
class Status:
    magnet: bool
    fault: bool


class STM32MagnetUART:
    def __init__(self, transport: Transport):
        self._transport = transport
        self._opened = False

    def open(self) -> None:
        self._transport.open()
        self._opened = True
        try:
            response = self._command("MAGNET_OFF")
            if response != "OK OFF":
                raise RuntimeError(f"unexpected safe-off response: {response!r}")
        except Exception:
            self._emergency_best_effort()
            self._transport.close()
            self._opened = False
            raise

    def _command(self, command: str) -> str:
        if not self._opened:
            raise RuntimeError("client is not open")
        self._transport.write_line(command)
        return self._transport.read_line()

    def ping(self) -> bool:
        return self._command("PING") == "PONG"

    def get_status(self) -> Status:
        response = self._command("GET_STATUS")
        prefix = "STATUS MAGNET="
        if not response.startswith(prefix) or " FAULT=" not in response:
            raise RuntimeError(f"invalid status response: {response!r}")
        magnet_text, fault_text = response[len(prefix):].split(" FAULT=", 1)
        if magnet_text not in {"0", "1"} or fault_text not in {"0", "1"}:
            raise RuntimeError(f"invalid status values: {response!r}")
        return Status(magnet=magnet_text == "1", fault=fault_text == "1")

    def magnet_on(self, timeout_ms: int) -> None:
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
            raise TypeError("timeout_ms must be an integer")
        if not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
            raise ValueError("timeout_ms must be between 50 and 500")
        response = self._command(f"MAGNET_ON {timeout_ms}")
        if response != f"OK ON TIMEOUT_MS={timeout_ms}":
            self._emergency_best_effort()
            raise RuntimeError(f"unexpected MAGNET_ON response: {response!r}")

    def magnet_off(self) -> None:
        if self._command("MAGNET_OFF") != "OK OFF":
            self._emergency_best_effort()
            raise RuntimeError("MAGNET_OFF was not acknowledged")

    def emergency_off(self) -> None:
        if self._command("EMERGENCY_OFF") != "OK OFF":
            raise RuntimeError("EMERGENCY_OFF was not acknowledged")

    def _emergency_best_effort(self) -> None:
        if self._opened:
            try:
                self._transport.write_line("EMERGENCY_OFF")
                self._transport.read_line()
            except Exception:
                pass

    def close(self) -> None:
        if self._opened:
            try:
                self.magnet_off()
            except Exception:
                self._emergency_best_effort()
            finally:
                self._transport.close()
                self._opened = False

    def __enter__(self) -> "STM32MagnetUART":
        self.open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if exc is not None:
            self._emergency_best_effort()
        self.close()


def preferred_linux_port() -> Optional[str]:
    by_id = Path("/dev/serial/by-id")
    if not by_id.is_dir():
        return None
    candidates = sorted(str(path) for path in by_id.iterdir())
    return candidates[0] if len(candidates) == 1 else None

