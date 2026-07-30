"""腕部纸面内旋转映射；禁止静默截断。"""

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
    roll_min_deg: float,
    roll_max_deg: float,
) -> WristRotationResult:
    if not roll_min_deg <= pick_roll_deg <= roll_max_deg:
        return WristRotationResult(
            valid=False,
            pick_roll_deg=float(pick_roll_deg),
            release_roll_deg=None,
            motion_deg=None,
            candidate_angles=[],
            rejection_reason="WRIST_PICK_ROLL_OUT_OF_RANGE",
        )
    nominal = float(pick_roll_deg) + float(wrist_roll_sign) * float(rotation_delta_deg)
    candidates = [nominal, nominal + 360.0, nominal - 360.0]
    feasible: list[tuple[float, float]] = []
    for angle in candidates:
        if roll_min_deg <= angle <= roll_max_deg:
            motion = abs(angle - pick_roll_deg)
            feasible.append((motion, angle))
    if not feasible:
        return WristRotationResult(
            valid=False,
            pick_roll_deg=float(pick_roll_deg),
            release_roll_deg=None,
            motion_deg=None,
            candidate_angles=candidates,
            rejection_reason="WRIST_ROTATION_OUT_OF_RANGE",
        )
    feasible.sort(key=lambda item: item[0])
    motion, chosen = feasible[0]
    return WristRotationResult(
        valid=True,
        pick_roll_deg=float(pick_roll_deg),
        release_roll_deg=float(chosen),
        motion_deg=float(motion),
        candidate_angles=candidates,
        rejection_reason=None,
    )
