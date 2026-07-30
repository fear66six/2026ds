"""白色碎片分割：Lab 亮度 + 低饱和 + 局部对比度（配置化阈值）。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from . import config


# 分割阈值（可被 runtime 覆盖）
LAB_L_MIN = 160
HSV_S_MAX = 80
HSV_V_MIN = 110
LOCAL_CONTRAST_MIN = 18
MORPH_KERNEL = 3


def segment_white_pieces(
    frame_bgr: np.ndarray,
    *,
    valid_roi: np.ndarray | None = None,
    debug_dir: Path | None = None,
) -> np.ndarray:
    """返回二值 mask（255=候选白片）。"""
    lab = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    l_chan = lab[:, :, 0]
    s_chan = hsv[:, :, 1]
    v_chan = hsv[:, :, 2]

    _, lab_mask = cv2.threshold(l_chan, LAB_L_MIN, 255, cv2.THRESH_BINARY)
    hsv_mask = cv2.inRange(hsv, (0, 0, HSV_V_MIN), (180, HSV_S_MAX, 255))

    blur = cv2.GaussianBlur(l_chan, (31, 31), 0)
    contrast = cv2.subtract(l_chan, blur)
    _, local_mask = cv2.threshold(contrast, LOCAL_CONTRAST_MIN, 255, cv2.THRESH_BINARY)

    combined = cv2.bitwise_and(lab_mask, hsv_mask)
    combined = cv2.bitwise_and(combined, local_mask)
    if valid_roi is not None:
        combined = cv2.bitwise_and(combined, valid_roi)

    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (MORPH_KERNEL, MORPH_KERNEL))
    morph = cv2.morphologyEx(combined, cv2.MORPH_OPEN, k, iterations=1)
    morph = cv2.morphologyEx(morph, cv2.MORPH_CLOSE, k, iterations=1)

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "lab_l.png"), l_chan)
        cv2.imwrite(str(debug_dir / "hsv_mask.png"), hsv_mask)
        cv2.imwrite(str(debug_dir / "local_contrast.png"), contrast)
        cv2.imwrite(str(debug_dir / "combined_mask.png"), combined)
        cv2.imwrite(str(debug_dir / "morphology_mask.png"), morph)

    return morph


def coarse_to_fine_contours(
    rectified_bgr: np.ndarray,
    *,
    scale: float = 0.5,
    pad_px: int = 12,
    debug_dir: Path | None = None,
) -> list[np.ndarray]:
    """返回高分辨率白片轮廓，低分辨率结果仅用于诊断。

    旧实现按每个低分辨率连通域分别扩大 ROI，再在 ROI 中取最大轮廓。
    同一块白片被分成多个粗连通域时会重复返回，而细长白片如果在缩放时
    断裂则会被完全漏掉。正式匹配需要恰好覆盖四块，因此以全分辨率分割
    为权威结果；840x1188 的标定图上该开销可接受。
    """
    h, w = rectified_bgr.shape[:2]
    small = cv2.resize(rectified_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    coarse_mask = segment_white_pieces(small, debug_dir=None)
    full_mask = segment_white_pieces(rectified_bgr, debug_dir=debug_dir)
    refined_contours, _ = cv2.findContours(
        full_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_NONE,
    )
    refined_contours = [
        cnt for cnt in refined_contours if cv2.contourArea(cnt) >= 200.0
    ]

    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "coarse_mask.png"), coarse_mask)
        candidate_vis = rectified_bgr.copy()
        for cnt in refined_contours:
            x, y, bw, bh = cv2.boundingRect(cnt)
            cv2.rectangle(
                candidate_vis,
                (max(0, x - pad_px), max(0, y - pad_px)),
                (min(w - 1, x + bw + pad_px), min(h - 1, y + bh + pad_px)),
                (0, 255, 255),
                1,
            )
        cv2.imwrite(str(debug_dir / "candidate_rois.png"), candidate_vis)
        refined_vis = np.zeros(rectified_bgr.shape[:2], dtype=np.uint8)
        cv2.drawContours(refined_vis, refined_contours, -1, 255, -1)
        cv2.imwrite(str(debug_dir / "refined_mask.png"), refined_vis)

    return refined_contours
