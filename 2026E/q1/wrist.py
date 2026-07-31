"""腕部纸面内旋转映射。"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class WristRotationResult:
    valid: bool
    pick_roll_deg: float
    release_roll_deg: float | None
    motion_deg: float | None
    candidate_angles: list[float]
    rejection_reason: str | None


def normalize_angle_deg(angle: float) -> float:
    normalized = float(((angle + 180.0) % 360.0) - 180.0)
    return 180.0 if normalized == -180.0 else normalized


def smaller_azimuth_angle_deg(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
) -> float:
    azimuth0 = math.degrees(math.atan2(float(y0), float(x0)))
    azimuth1 = math.degrees(math.atan2(float(y1), float(x1)))
    return abs(normalize_angle_deg(azimuth1 - azimuth0))


def swing_roll_compensation_deg(
    pick_xy: tuple[float, float],
    release_xy: tuple[float, float],
    *,
    sign: float = -1.0,
) -> float:
    swing = smaller_azimuth_angle_deg(
        pick_xy[0],
        pick_xy[1],
        release_xy[0],
        release_xy[1],
    )
    return float(sign) * swing


def choose_wrist_release_roll(
    *,
    pick_roll_deg: float,
    rotation_delta_deg: float,
    wrist_roll_sign: float,
) -> WristRotationResult:
    motion = float(wrist_roll_sign) * normalize_angle_deg(rotation_delta_deg)
    chosen = float(pick_roll_deg) + motion
    return WristRotationResult(
        valid=True,
        pick_roll_deg=float(pick_roll_deg),
        release_roll_deg=float(chosen),
        motion_deg=abs(float(motion)),
        candidate_angles=[float(chosen)],
        rejection_reason=None,
    )
