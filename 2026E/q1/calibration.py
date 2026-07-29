"""A4透视标定与纸面坐标到机械臂坐标的显式门禁。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .models import RobotPose


@dataclass
class PaperCalibration:
    image_size: tuple[int, int]
    corners_px: np.ndarray
    output_size: tuple[int, int] = (840, 1188)

    def __post_init__(self) -> None:
        w, h = self.output_size
        dst = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], np.float32)
        self.matrix = cv2.getPerspectiveTransform(self.corners_px.astype(np.float32), dst)
        self.inverse_matrix = np.linalg.inv(self.matrix)
        self._scaled_cache: dict[tuple[int, int], "PaperCalibration"] = {}

    @classmethod
    def load(cls, path: Path) -> "PaperCalibration":
        data = json.loads(path.read_text(encoding="utf-8"))
        size = data.get("camera_resolution") or data.get("image_size")
        corners = data.get("corners_px") or data.get("corners")
        output = data.get("target_size_px") or data.get("output_size") or [840, 1188]
        if not size or not corners:
            raise ValueError("纸面标定缺少图像尺寸或四角")
        return cls(tuple(map(int, size)), np.asarray(corners, np.float32), tuple(map(int, output)))

    def scaled_for(self, frame_shape: tuple[int, ...]) -> "PaperCalibration":
        h, w = frame_shape[:2]
        old_w, old_h = self.image_size
        if (w, h) == (old_w, old_h):
            return self
        if (w, h) in self._scaled_cache:
            return self._scaled_cache[(w, h)]
        sx, sy = w / old_w, h / old_h
        if abs(sx - sy) > 0.01:
            raise ValueError("CALIBRATION_REQUIRED: 摄像头宽高比例与标定不一致")
        corners = self.corners_px * np.array([sx, sy], np.float32)
        scaled = PaperCalibration((w, h), corners, self.output_size)
        self._scaled_cache[(w, h)] = scaled
        return scaled

    def rectify(self, frame: np.ndarray) -> np.ndarray:
        calibration = self.scaled_for(frame.shape)
        return cv2.warpPerspective(frame, calibration.matrix, calibration.output_size)

    def transform_points(self, points: np.ndarray) -> np.ndarray:
        return cv2.perspectiveTransform(np.asarray(points, np.float32).reshape(-1, 1, 2), self.matrix).reshape(-1, 2)


class ArmCoordinateMapper:
    """只接受磁盘中的显式标定矩阵，不提供虚假默认矩阵。"""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._matrix: np.ndarray | None = None
        self.wrist_roll_zero_deg: float | None = None
        self.wrist_roll_sign: float | None = None
        self.wrist_roll_min_deg: float | None = None
        self.wrist_roll_max_deg: float | None = None
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
            if "wrist_roll_min_deg" in data:
                self.wrist_roll_min_deg = float(data["wrist_roll_min_deg"])
            if "wrist_roll_max_deg" in data:
                self.wrist_roll_max_deg = float(data["wrist_roll_max_deg"])
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
            and self.wrist_roll_min_deg is not None
            and self.wrist_roll_max_deg is not None
        )

    def map_in_plane_rotation(self, delta_deg: float) -> float:
        if not self.wrist_mapping_ready():
            raise RuntimeError("CALIBRATION_REQUIRED: 缺少腕部 roll 零位/方向/范围标定")
        roll = float(self.wrist_roll_zero_deg) + float(self.wrist_roll_sign) * float(delta_deg)
        roll = max(float(self.wrist_roll_min_deg), min(float(self.wrist_roll_max_deg), roll))
        return roll

    def paper_to_robot(self, x_mm: float, y_mm: float, z_mm: float) -> RobotPose:
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
            0.0,
            self.default_claw,
            0,
        )
