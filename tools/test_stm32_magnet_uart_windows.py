"""Safe Windows runtime test: MAGNET_OFF, PING, and GET_STATUS only.

This script is not run automatically. It never sends MAGNET_ON.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from drivers.stm32_magnet_uart import (  # noqa: E402
    MockTransport,
    STM32MagnetUART,
    SerialTransport,
)


def find_ch343_port() -> str:
    from serial.tools import list_ports

    candidates = [
        item.device
        for item in list_ports.comports()
        if (item.vid, item.pid) == (0x1A86, 0x55D3)
        or "CH343" in (item.description or "").upper()
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"expected one CH343 port, found: {candidates}")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="Explicit Windows COM port, e.g. COM15")
    parser.add_argument("--mock", action="store_true", help="No hardware access")
    args = parser.parse_args()

    if args.mock:
        transport = MockTransport()
        label = "mock"
    else:
        port = args.port or find_ch343_port()
        transport = SerialTransport(port=port)
        label = port

    with STM32MagnetUART(transport) as client:
        successes = sum(1 for _ in range(10) if client.ping())
        status = client.get_status()
        print(f"transport={label}")
        print(f"ping_success={successes}/10")
        print(f"magnet={int(status.magnet)} fault={int(status.fault)}")
        if successes != 10 or status.magnet:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
