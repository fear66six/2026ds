"""纸面坐标到机械臂坐标的显式门禁。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .models import RobotPose
from .wrist import WristRotationResult, choose_wrist_release_roll


class ArmCoordinateMapper:
    """只接受磁盘中的显式标定矩阵，不提供虚假默认矩阵。"""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._matrix: np.ndarray | None = None
        self.wrist_roll_zero_deg: float | None = None
        self.wrist_roll_sign: float | None = None
        self.default_pitch_deg: float = -90.0
        self.default_claw: float = 0.0
        if path is not None and path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            matrix = np.asarray(data.get("paper_to_robot_matrix"), dtype=np.float64)
            if matrix.shape not in ((3, 3), (4, 4)):
                raise ValueError("机械臂标定矩阵必须为3x3或4x4")
            self._matrix = matrix
            if "wrist_roll_zero_deg" in data:
                self.wrist_roll_zero_deg = float(data["wrist_roll_zero_deg"])
            if "wrist_roll_sign" in data:
                self.wrist_roll_sign = float(data["wrist_roll_sign"])
            if "default_pitch_deg" in data:
                self.default_pitch_deg = float(data["default_pitch_deg"])
            if "default_claw" in data:
                self.default_claw = float(data["default_claw"])

    def is_calibrated(self) -> bool:
        return self._matrix is not None

    def wrist_mapping_ready(self) -> bool:
        return (
            self.wrist_roll_zero_deg is not None
            and self.wrist_roll_sign is not None
        )

    def map_in_plane_rotation(
        self, delta_deg: float, *, pick_roll_deg: float | None = None
    ) -> WristRotationResult:
        if not self.wrist_mapping_ready():
            raise RuntimeError("CALIBRATION_REQUIRED: 缺少腕部 roll 零位/方向标定")
        pick = float(self.wrist_roll_zero_deg if pick_roll_deg is None else pick_roll_deg)
        return choose_wrist_release_roll(
            pick_roll_deg=pick,
            rotation_delta_deg=float(delta_deg),
            wrist_roll_sign=float(self.wrist_roll_sign),
        )

    def paper_to_robot(
        self, x_mm: float, y_mm: float, z_mm: float, *, roll_deg: float = 0.0
    ) -> RobotPose:
        if self._matrix is None:
            raise RuntimeError("CALIBRATION_REQUIRED")
        if self._matrix.shape == (3, 3):
            out = self._matrix @ np.array([x_mm, y_mm, 1.0])
            rx, ry = out[:2] / out[2]
            rz = z_mm
        else:
            out = self._matrix @ np.array([x_mm, y_mm, z_mm, 1.0])
            rx, ry, rz = out[:3] / out[3]
        return RobotPose(
            float(rx),
            float(ry),
            float(rz),
            self.default_pitch_deg,
            float(roll_deg),
            self.default_claw,
            0,
        )
