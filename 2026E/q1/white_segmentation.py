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
    """低分辨率定位候选，高分辨率 ROI 精修轮廓。"""
    h, w = rectified_bgr.shape[:2]
    small = cv2.resize(rectified_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    coarse_mask = segment_white_pieces(small, debug_dir=None)
    if debug_dir is not None:
        debug_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(debug_dir / "coarse_mask.png"), coarse_mask)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(coarse_mask, connectivity=8)
    refined_contours: list[np.ndarray] = []
    roi_vis = rectified_bgr.copy()
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if area < 40:
            continue
        # 映射回高分辨率并扩边
        x0 = max(0, int(x / scale) - pad_px)
        y0 = max(0, int(y / scale) - pad_px)
        x1 = min(w, int((x + bw) / scale) + pad_px)
        y1 = min(h, int((y + bh) / scale) + pad_px)
        roi = rectified_bgr[y0:y1, x0:x1]
        if roi.size == 0:
            continue
        fine_mask = segment_white_pieces(roi)
        contours, _ = cv2.findContours(fine_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        cnt = cnt + np.array([[[x0, y0]]], dtype=cnt.dtype)
        refined_contours.append(cnt)
        cv2.rectangle(roi_vis, (x0, y0), (x1, y1), (0, 255, 255), 1)

    if debug_dir is not None:
        cv2.imwrite(str(debug_dir / "candidate_rois.png"), roi_vis)
        refined_vis = np.zeros(rectified_bgr.shape[:2], dtype=np.uint8)
        cv2.drawContours(refined_vis, refined_contours, -1, 255, -1)
        cv2.imwrite(str(debug_dir / "refined_mask.png"), refined_vis)

    return refined_contours
