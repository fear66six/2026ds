"""腕部纸面内旋转映射。"""

from __future__ import annotations

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
    return float(((angle + 180.0) % 360.0) - 180.0)


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
