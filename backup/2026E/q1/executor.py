"""下位机执行器：串口发送拼接指令（实际驱动物理装置）"""

from __future__ import annotations

import time
from typing import Optional

from . import config
from .motion import MotionStep, Phase


class DeviceExecutor:
    """
    与 MCU 通信的简单文本协议（115200）：

        PING        → PONG
        HOME        → OK
        PICK x y    → OK   移动到碎片上方并抓取 (cm)
        MOVE x y a  → OK   搬运并旋转 a 度（禁止翻转，由上位机算好）
        PLACE       → OK   释放碎片
        DONE        → OK   声光完成指示

    下位机只需解析上述命令并驱动步进/舵机/吸盘即可。
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baud: int | None = None,
        dry_run: bool = False,
        step_delay_s: float | None = None,
    ):
        self.port = port or config.SERIAL_PORT
        self.baud = baud or config.SERIAL_BAUD
        self.dry_run = dry_run or config.FORCE_DRY_RUN
        self.step_delay_s = step_delay_s if step_delay_s is not None else config.STEP_DELAY_S
        self._ser = None

        if not self.dry_run:
            self._open_serial()

    def _open_serial(self) -> None:
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError("请安装 pyserial: pip install pyserial") from exc

        if not self.port:
            raise RuntimeError("未指定串口，请使用 --port COM3 或设置 config.SERIAL_PORT")

        self._ser = serial.Serial(self.port, self.baud, timeout=config.SERIAL_TIMEOUT_S)
        time.sleep(0.3)
        if not self.ping():
            raise RuntimeError(f"下位机无响应: {self.port}")

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            self._ser.close()
        self._ser = None

    def _send(self, cmd: str) -> str:
        line = cmd.strip()
        print(f"[MCU] >> {line}")
        if self.dry_run:
            time.sleep(self.step_delay_s)
            print("[MCU] << OK (dry-run)")
            return "OK"

        assert self._ser is not None
        self._ser.write((line + "\n").encode("utf-8"))
        self._ser.flush()
        resp = self._ser.readline().decode("utf-8", errors="ignore").strip()
        print(f"[MCU] << {resp}")
        if resp.startswith("ERR"):
            raise RuntimeError(resp)
        return resp

    def ping(self) -> bool:
        if self.dry_run:
            return True
        try:
            resp = self._send("PING")
            return resp.upper() == "PONG"
        except Exception:
            return False

    def home(self) -> None:
        self._send("HOME")

    def execute_step(self, step: MotionStep) -> None:
        if step.phase == Phase.DONE:
            self._send("DONE")
            return

        x0, y0 = step.from_cm
        x1, y1 = step.to_cm
        self._send(f"PICK {x0:.2f} {y0:.2f}")
        self._send(f"MOVE {x1:.2f} {y1:.2f} {step.angle_deg:.2f}")
        self._send("PLACE")

    def run_all(self, steps: list[MotionStep]) -> None:
        self.home()
        for step in steps:
            self.execute_step(step)
