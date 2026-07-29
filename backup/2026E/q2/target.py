"""推断第二问目标矩形尺寸 (9×5 ~ 12×9 cm)"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from . import config
from .piece import AnalyzedPiece


def candidate_target_sizes(total_area: float) -> List[Tuple[float, float, float]]:
    cands: List[Tuple[float, float, float]] = []
    step = 0.25
    w_vals = np.arange(config.TARGET_WIDTH_MIN_CM, config.TARGET_WIDTH_MAX_CM + step / 2, step)
    h_vals = np.arange(config.TARGET_HEIGHT_MIN_CM, config.TARGET_HEIGHT_MAX_CM + step / 2, step)
    for w in w_vals:
        for h in h_vals:
            target_area = w * h
            rel_err = abs(target_area - total_area) / max(total_area, 1e-6)
            if rel_err <= config.AREA_SUM_TOLERANCE:
                cands.append((float(w), float(h), rel_err))
    cands.sort(key=lambda x: x[2])
    if not cands:
        w = float(np.clip(np.sqrt(total_area * 1.2), config.TARGET_WIDTH_MIN_CM, config.TARGET_WIDTH_MAX_CM))
        h = float(np.clip(total_area / w, config.TARGET_HEIGHT_MIN_CM, config.TARGET_HEIGHT_MAX_CM))
        cands.append((w, h, abs(w * h - total_area) / max(total_area, 1e-6)))
    return cands


def infer_target_size(
    pieces: List[AnalyzedPiece],
    width_hint: Optional[float] = None,
    height_hint: Optional[float] = None,
) -> Tuple[float, float]:
    total = sum(p.area_cm2 for p in pieces)
    if width_hint and height_hint:
        return float(width_hint), float(height_hint)
    if width_hint:
        return float(width_hint), float(np.clip(total / width_hint, config.TARGET_HEIGHT_MIN_CM, config.TARGET_HEIGHT_MAX_CM))
    if height_hint:
        return float(np.clip(total / height_hint, config.TARGET_WIDTH_MIN_CM, config.TARGET_WIDTH_MAX_CM)), float(height_hint)

    cands = candidate_target_sizes(total)
    return cands[0][0], cands[0][1]


def target_origin_for_size(width_cm: float) -> Tuple[float, float]:
    ox = (config.A4_WIDTH_CM - width_cm) / 2.0
    oy = config.TARGET_ORIGIN_Y_CM
    return float(ox), float(oy)
