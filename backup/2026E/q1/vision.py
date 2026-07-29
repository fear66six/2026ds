"""视觉检测：A4 标定、分界线、碎片轮廓"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

from . import config
from .geometry import resample_polygon


@dataclass
class DetectedPiece:
    contour: np.ndarray
    center_cm: Tuple[float, float]
    angle_deg: float
    area_cm2: float
    vertices_cm: np.ndarray
    bbox_cm: Tuple[float, float, float, float]  # x, y, w, h
    in_upper_half: bool


@dataclass
class PaperFrame:
    corners_px: np.ndarray  # 4x2 ordered: TL, TR, BR, BL
    px_per_cm: float
    divider_y_cm: float = config.DIVIDER_Y_CM
    landscape_in_image: bool = False  # 摄像头里纸垫呈横向（非 A4 竖向像素比例）


def _order_corners(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def detect_paper(frame: np.ndarray) -> Optional[PaperFrame]:
    """检测 A4 纸外轮廓并估算 px/cm（黑底场景）"""
    return _detect_paper_dark(frame)


def _a4_aspect_ratio(width_px: float, height_px: float) -> float:
    return width_px / max(height_px, 1.0)


def _a4_aspect_portrait() -> float:
    return config.A4_WIDTH_CM / config.A4_HEIGHT_CM


def _a4_aspect_landscape() -> float:
    return config.A4_HEIGHT_CM / config.A4_WIDTH_CM


def _bbox_aspect_ok(bw: int, bh: int) -> bool:
    aspect = bw / max(bh, 1)
    tol = config.MAT_ASPECT_TOL
    return (
        abs(aspect - _a4_aspect_portrait()) <= tol
        or abs(aspect - _a4_aspect_landscape()) <= tol
    )


def _corners_landscape_in_image(corners: np.ndarray) -> bool:
    width_px = float(np.linalg.norm(corners[1] - corners[0]))
    height_px = float(np.linalg.norm(corners[3] - corners[0]))
    return width_px > height_px * 1.05


def _a4_cm_plane_corners(landscape_in_image: bool) -> np.ndarray:
    """透视标定用的 cm 四角（与图像 TL,TR,BR,BL 对应）"""
    if landscape_in_image:
        return np.array(
            [[0, 0], [config.A4_HEIGHT_CM, 0], [config.A4_HEIGHT_CM, config.A4_WIDTH_CM], [0, config.A4_WIDTH_CM]],
            dtype=np.float32,
        )
    return np.array(
        [[0, 0], [config.A4_WIDTH_CM, 0], [config.A4_WIDTH_CM, config.A4_HEIGHT_CM], [0, config.A4_HEIGHT_CM]],
        dtype=np.float32,
    )


def _cm_from_plane(x_plane: float, y_plane: float, landscape_in_image: bool) -> Tuple[float, float]:
    """平面坐标转标准 A4 坐标系 (x=0..21, y=0..29.7)"""
    if landscape_in_image:
        return float(y_plane), float(x_plane)
    return float(x_plane), float(y_plane)


def _cm_to_plane(x_cm: float, y_cm: float, landscape_in_image: bool) -> Tuple[float, float]:
    if landscape_in_image:
        return float(y_cm), float(x_cm)
    return float(x_cm), float(y_cm)


def _find_paper_frame_from_content(gray: np.ndarray, thresh: int = 15) -> Optional[np.ndarray]:
    """
    从白线/白片等内容推断内框（仅作兜底，且拒绝整幅图误判）。
    """
    h, w = gray.shape
    xs = [w // 4, w // 2, 3 * w // 4]
    ys = [h // 4, h // 2, 3 * h // 4]

    tops, bottoms, lefts, rights = [], [], [], []
    for x in xs:
        for y in range(h):
            if gray[y, x] > thresh:
                tops.append(y)
                break
        for y in range(h - 1, -1, -1):
            if gray[y, x] > thresh:
                bottoms.append(y)
                break
    for y in ys:
        for x in range(w):
            if gray[y, x] > thresh:
                lefts.append(x)
                break
        for x in range(w - 1, -1, -1):
            if gray[y, x] > thresh:
                rights.append(x)
                break

    if not tops or not bottoms or not lefts or not rights:
        return None

    top = int(np.median(tops))
    bottom = int(np.median(bottoms))
    left = int(np.median(lefts))
    right = int(np.median(rights))
    width = right - left
    height = bottom - top
    if width < 50 or height < 50:
        return None

    # 整幅图误判：画面不是 A4 竖向铺满时，内容扫描会把杂物也算进来
    if width > w * 0.88 and height > h * 0.88:
        return None

    ratio = _a4_aspect_ratio(width, height)
    expected_p = _a4_aspect_portrait()
    expected_l = _a4_aspect_landscape()
    if abs(ratio - expected_p) > config.MAT_ASPECT_TOL and abs(ratio - expected_l) > config.MAT_ASPECT_TOL:
        return None

    return np.array(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=np.float32,
    )


def _bbox_border_touches(x: float, y: float, bw: float, bh: float, w: int, h: int, margin: int = 8) -> int:
    n = 0
    if x <= margin:
        n += 1
    if y <= margin:
        n += 1
    if x + bw >= w - margin:
        n += 1
    if y + bh >= h - margin:
        n += 1
    return n


def _corners_border_touches(corners: np.ndarray, w: int, h: int, margin: int = 8) -> int:
    x0 = float(corners[:, 0].min())
    y0 = float(corners[:, 1].min())
    x1 = float(corners[:, 0].max())
    y1 = float(corners[:, 1].max())
    return _bbox_border_touches(x0, y0, x1 - x0, y1 - y0, w, h, margin)


def _tighten_merge_bounds(boxes: list, w: int, h: int) -> Tuple[int, int, int, int]:
    """合并上下两块时收紧左右边界，避免贴屏幕边缘的误检"""
    lefts = [b[1] for b in boxes[:2]]
    rights = [b[1] + b[3] for b in boxes[:2]]
    if min(lefts) <= 8 and max(lefts) > 20:
        x0 = max(lefts)
    else:
        x0 = min(lefts)
    if max(rights) >= w - 8:
        x1 = min(rights)
    else:
        x1 = max(rights)
    y0 = min(b[2] for b in boxes[:2])
    y1 = max(b[2] + b[4] for b in boxes[:2])
    return x0, y0, x1, y1


def _contour_touches_image_border(pts: np.ndarray, w: int, h: int, margin: int = 8) -> bool:
    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)
    return (
        x_min <= margin
        or y_min <= margin
        or x_max >= w - margin
        or y_max >= h - margin
    )


def _detect_mat_bbox_frame(gray: np.ndarray) -> Optional[np.ndarray]:
    """从黑纸垫外接矩形标定工作区（支持画面里横向/竖向，排除左侧杂物）"""
    return _detect_outer_mat_frame(gray)


def _detect_outer_mat_frame(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    第一步：检测外部黑纸垫矩形框。
    画面里可能是 A4 竖向或横向像素比例，均接受。
    """
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(blur, config.BLACK_PAPER_GRAY_THRESH, 255, cv2.THRESH_BINARY_INV)

    if w >= h and config.CAMERA_CROP_LEFT_FRAC > 0:
        dark[:, : int(w * config.CAMERA_CROP_LEFT_FRAC)] = 0

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _merge_stacked_paper_frame(gray)

    img_area = h * w
    best_box = None
    best_score = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        frac = area / img_area
        if frac < config.MAT_MIN_AREA_FRAC or frac > config.MAT_MAX_AREA_FRAC:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if bw < 80 or bh < 80:
            continue
        if not _bbox_aspect_ok(bw, bh):
            continue
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.025 * peri, True)
        rect_bonus = 1.15 if len(approx) == 4 else 1.0
        score = area * rect_bonus
        if score > best_score:
            best_score = score
            best_box = (x, y, bw, bh)

    if best_box is not None:
        x, y, bw, bh = best_box
        return np.array(
            [[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]],
            dtype=np.float32,
        )

    merged = _merge_stacked_paper_frame(gray)
    if merged is not None:
        return merged
    return None


def _inner_roi_mask(paper: PaperFrame, shape: Tuple[int, ...]) -> np.ndarray:
    """纸垫内侧多边形 ROI：仅在此区域内检测碎片，排除框外杂物"""
    h, w = shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    inset = max(6, int(paper.px_per_cm * config.MAT_INSET_CM))
    pts = paper.corners_px.astype(np.float32)
    cx, cy = pts.mean(axis=0)
    inner = pts.copy()
    for i in range(4):
        v = inner[i] - np.array([cx, cy], dtype=np.float32)
        ln = float(np.linalg.norm(v))
        if ln > inset:
            inner[i] = inner[i] - v / ln * inset
    cv2.fillConvexPoly(mask, inner.astype(np.int32), 255)
    return mask


def _point_in_paper_roi(pt_px: Tuple[float, float], paper: PaperFrame, shape: Tuple[int, ...]) -> bool:
    roi = _inner_roi_mask(paper, shape)
    x, y = int(round(pt_px[0])), int(round(pt_px[1]))
    if x < 0 or y < 0 or x >= roi.shape[1] or y >= roi.shape[0]:
        return False
    return roi[y, x] > 0


def _divider_y_px(paper: PaperFrame, divider_y_cm: float) -> int:
    return int(
        paper.corners_px[0, 1]
        + (divider_y_cm / config.A4_HEIGHT_CM)
        * (paper.corners_px[3, 1] - paper.corners_px[0, 1])
    )


def filter_upper_half_pieces(
    pieces: List[DetectedPiece],
    paper: PaperFrame,
    divider_y_cm: float,
) -> List[DetectedPiece]:
    """上半区：以检测到的分界线 cm 坐标为准"""
    band_cm = 0.6
    min_area = config.MIN_PIECE_AREA_CM2
    out: List[DetectedPiece] = []
    for piece in pieces:
        if piece.area_cm2 < min_area:
            continue
        if piece.center_cm[1] < divider_y_cm + band_cm * 0.15:
            out.append(piece)
    return out


def _detect_paper_dark(frame: np.ndarray) -> Optional[PaperFrame]:
    """黑底场景：先检测外部黑纸垫矩形，再用于内部标定"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = frame.shape[:2]

    merged = _merge_stacked_paper_frame(gray)
    outer = _detect_outer_mat_frame(gray)

    if merged is not None and outer is not None:
        mh = float(merged[3, 1] - merged[0, 1])
        oh = float(outer[3, 1] - outer[0, 1])
        best = merged if mh > oh * 1.20 else outer
    elif merged is not None:
        best = merged
    elif outer is not None:
        best = outer
    else:
        best = None

    if best is not None and _corners_border_touches(best, w, h) >= 3:
        if outer is not None and _corners_border_touches(outer, w, h) < 3:
            best = outer

    if best is not None and _corners_border_touches(best, w, h) >= 3:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, dark = cv2.threshold(blur, config.BLACK_PAPER_GRAY_THRESH, 255, cv2.THRESH_BINARY_INV)
        if w >= h and config.CAMERA_CROP_LEFT_FRAC > 0:
            dark[:, : int(w * config.CAMERA_CROP_LEFT_FRAC)] = 0
        contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        img_area = h * w
        boxes = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < img_area * 0.06:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            if _bbox_aspect_ok(bw, bh) or area >= img_area * 0.20:
                boxes.append((area, x, y, bw, bh))
        if len(boxes) >= 2:
            boxes.sort(key=lambda b: b[2])
            x0, y0, x1, y1 = _tighten_merge_bounds(boxes, w, h)
            if x1 - x0 > 80 and y1 - y0 > 80:
                best = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]], dtype=np.float32)

    if best is None:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, dark = cv2.threshold(blur, config.BLACK_PAPER_GRAY_THRESH, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        img_area = h * w
        best_score = 0.0
        quad_best = None

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < img_area * config.MAT_MIN_AREA_FRAC:
                continue
            x, y, bw, bh = cv2.boundingRect(cnt)
            if not _bbox_aspect_ok(bw, bh):
                continue
            peri = cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
            if len(approx) < 4:
                continue
            if len(approx) > 4:
                approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
            if len(approx) != 4:
                continue
            pts = approx.reshape(-1, 2).astype(np.float32)
            if _contour_touches_image_border(pts, w, h) and area < img_area * 0.35:
                continue
            if area > best_score:
                best_score = area
                quad_best = pts

        best = quad_best

    if best is None:
        content_frame = _find_paper_frame_from_content(gray, thresh=8)
        if content_frame is not None:
            best = content_frame
        else:
            return None

    ordered = _order_corners(best)
    landscape = _corners_landscape_in_image(ordered)
    px_per_cm = _paper_px_per_cm(ordered, landscape)
    return PaperFrame(
        corners_px=ordered,
        px_per_cm=px_per_cm,
        landscape_in_image=landscape,
    )


def _px_to_cm(pt_px: np.ndarray, paper: PaperFrame) -> Tuple[float, float]:
    """透视近似：将像素映射到标准 A4 cm 坐标 (x:0..21, y:0..29.7)"""
    dst = _a4_cm_plane_corners(paper.landscape_in_image)
    M = cv2.getPerspectiveTransform(paper.corners_px.astype(np.float32), dst)
    pt = np.array([[[pt_px[0], pt_px[1]]]], dtype=np.float32)
    out = cv2.perspectiveTransform(pt, M)[0, 0]
    return _cm_from_plane(float(out[0]), float(out[1]), paper.landscape_in_image)


def contour_to_cm(contour: np.ndarray, paper: PaperFrame) -> np.ndarray:
    """轮廓像素点映射到 cm 坐标"""
    pts = []
    for p in contour.reshape(-1, 2):
        pts.append(_px_to_cm(p, paper))
    return np.array(pts, dtype=np.float64)


def _contour_to_cm(contour: np.ndarray, paper: PaperFrame) -> np.ndarray:
    return contour_to_cm(contour, paper)


def detect_divider_line(frame: np.ndarray, paper: PaperFrame) -> Optional[float]:
    """检测水平分界线，返回 y 坐标 (cm)"""
    return _detect_divider_bright(frame, paper)


def _detect_divider_bright(frame: np.ndarray, paper: PaperFrame) -> Optional[float]:
    """黑底白线分界线"""
    y_px = int(paper.corners_px[0, 1] + (paper.corners_px[3, 1] - paper.corners_px[0, 1]) * 0.5)
    x0 = int(paper.corners_px[0, 0])
    x1 = int(paper.corners_px[1, 0])
    roi = frame[max(0, y_px - 40) : y_px + 40, x0:x1]
    if roi.size == 0:
        return config.DIVIDER_Y_CM

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, bright = cv2.threshold(gray, config.WHITE_DIVIDER_GRAY_THRESH, 255, cv2.THRESH_BINARY)
    lines = cv2.HoughLinesP(bright, 1, np.pi / 180, 40, minLineLength=60, maxLineGap=15)
    if lines is None:
        return config.DIVIDER_Y_CM

    best_y = None
    best_len = 0
    y_offset = max(0, y_px - 40)
    for line in lines.reshape(-1, 4):
        x1l, y1l, x2l, y2l = line
        if abs(y2l - y1l) > 10:
            continue
        length = abs(x2l - x1l)
        if length > best_len:
            best_len = length
            best_y = (y1l + y2l) / 2 + y_offset

    if best_y is None:
        return config.DIVIDER_Y_CM

    _, y_cm = _px_to_cm(np.array([x0, best_y]), paper)
    return y_cm


def _watershed_split_blob(sub: np.ndarray, n_expected: int = 2, fg_frac: float = 0.38) -> np.ndarray:
    sub = (sub > 0).astype(np.uint8) * 255
    if not np.any(sub):
        return sub

    dist = cv2.distanceTransform(sub, cv2.DIST_L2, 5)
    peak = float(dist.max())
    if peak < 4.0:
        return sub

    _, sure_fg = cv2.threshold(dist, max(2.0, fg_frac * peak), 255, 0)
    sure_fg = np.uint8(sure_fg)
    unknown = cv2.subtract(sub, sure_fg)
    _, markers = cv2.connectedComponents(sure_fg)
    if markers.max() < 2:
        return sub

    markers = markers + 1
    markers[unknown == 255] = 0
    color = cv2.cvtColor(sub, cv2.COLOR_GRAY2BGR)
    cv2.watershed(color, markers)

    out = np.zeros_like(sub)
    kept = 0
    for lbl in range(2, markers.max() + 1):
        region = ((markers == lbl) & (sub > 0)).astype(np.uint8) * 255
        if cv2.countNonZero(region) < 80:
            continue
        out = cv2.bitwise_or(out, region)
        kept += 1
        if kept >= n_expected:
            break
    return out if cv2.countNonZero(out) > 0 else sub


def _split_contour_by_erode(
    cnt: np.ndarray,
    shape: Tuple[int, ...],
    paper: PaperFrame,
) -> List[np.ndarray]:
    """腐蚀分离粘连块，再膨胀回原始区域内"""
    sub = np.zeros(shape[:2], dtype=np.uint8)
    cv2.drawContours(sub, [cnt], -1, 255, thickness=-1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    min_px = max(200, int((paper.px_per_cm ** 2) * config.MIN_PIECE_AREA_CM2 * 0.5))

    for it in (1, 2, 3):
        eroded = cv2.erode(sub, kernel, iterations=it)
        seeds, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        seeds = [c for c in seeds if cv2.contourArea(c) >= min_px]
        if len(seeds) < 2:
            continue
        parts: List[np.ndarray] = []
        for seed in seeds:
            seed_mask = np.zeros_like(sub)
            cv2.drawContours(seed_mask, [seed], -1, 255, thickness=-1)
            grown = cv2.dilate(seed_mask, kernel, iterations=it + 3)
            piece_mask = cv2.bitwise_and(sub, grown)
            pcnts, _ = cv2.findContours(piece_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not pcnts:
                continue
            parts.append(max(pcnts, key=cv2.contourArea))
        if len(parts) >= 2:
            return parts
    return []


def _split_oversized_contour(
    cnt: np.ndarray,
    shape: Tuple[int, ...],
    paper: PaperFrame,
) -> List[np.ndarray]:
    area_cm2 = cv2.contourArea(cnt) / (paper.px_per_cm ** 2)
    max_single = config.MAX_PIECE_AREA_CM2 * 0.9
    n_target = max(2, min(4, int(round(area_cm2 / max_single))))

    sub = np.zeros(shape[:2], dtype=np.uint8)
    cv2.drawContours(sub, [cnt], -1, 255, thickness=-1)
    for frac in (0.38, 0.28, 0.20, 0.15):
        split = _watershed_split_blob(sub, n_expected=n_target, fg_frac=frac)
        cnts, _ = cv2.findContours(split, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = [c for c in cnts if cv2.contourArea(c) >= 200]
        if len(cnts) >= 2:
            return cnts

    eroded = _split_contour_by_erode(cnt, shape, paper)
    if len(eroded) >= 2:
        return eroded
    return []


def _contour_mean_gray(cnt: np.ndarray, frame: np.ndarray) -> float:
    x, y, w, h = cv2.boundingRect(cnt)
    if w <= 0 or h <= 0:
        return 0.0
    roi = frame[y : y + h, x : x + w]
    mask = np.zeros(roi.shape[:2], dtype=np.uint8)
    c2 = cnt.copy().astype(np.int32)
    c2[:, 0, 0] -= x
    c2[:, 0, 1] -= y
    cv2.drawContours(mask, [c2], -1, 255, thickness=-1)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    vals = gray[mask > 0]
    return float(np.mean(vals)) if len(vals) else 0.0


def _contour_shape_metrics(cnt: np.ndarray, frame: np.ndarray) -> Tuple[float, float, float]:
    area = cv2.contourArea(cnt)
    peri = cv2.arcLength(cnt, True)
    compactness = 4.0 * np.pi * area / max(peri * peri, 1.0)
    hull = cv2.convexHull(cnt)
    solidity = area / max(cv2.contourArea(hull), 1.0)
    mean_g = _contour_mean_gray(cnt, frame)
    return compactness, solidity, mean_g


def _is_glare_contour(cnt: np.ndarray, frame: np.ndarray) -> bool:
    """反光：灰度偏低 + 边缘毛糙/凹陷，不是纯白纸片"""
    area = cv2.contourArea(cnt)
    if area < 200:
        return True
    compactness, solidity, mean_g = _contour_shape_metrics(cnt, frame)
    if compactness < config.GLARE_MAX_COMPACTNESS and solidity < config.GLARE_MAX_SOLIDITY:
        return True
    if compactness < 0.22 and mean_g < config.GLARE_MAX_MEAN_GRAY:
        return True
    if solidity < 0.72 and mean_g < config.GLARE_MAX_MEAN_GRAY:
        return True
    return False


def _decompose_glare_mixed_blob(
    cnt: np.ndarray,
    frame: np.ndarray,
    paper: PaperFrame,
) -> List[np.ndarray]:
    """粘连块里分离真白片，丢弃反光区域"""
    x, y, w, h = cv2.boundingRect(cnt)
    if w <= 0 or h <= 0:
        return []
    roi = frame[y : y + h, x : x + w]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    cm = np.zeros((h, w), dtype=np.uint8)
    c2 = cnt.copy().astype(np.int32)
    c2[:, 0, 0] -= x
    c2[:, 0, 1] -= y
    cv2.drawContours(cm, [c2], -1, 255, thickness=-1)

    bright = cv2.inRange(
        hsv,
        np.array([0, 0, config.GLARE_BRIGHT_V_MIN]),
        np.array([180, 90, 255]),
    )
    bright = cv2.bitwise_and(bright, cm)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    bright = cv2.morphologyEx(bright, cv2.MORPH_OPEN, kernel, iterations=1)

    sub_cnts, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out: List[np.ndarray] = []
    for sub in sub_cnts:
        if cv2.contourArea(sub) < 200:
            continue
        sub_global = sub + np.array([[x, y]], dtype=np.int32)
        if _is_glare_contour(sub_global, frame):
            continue
        out.append(sub_global.astype(np.int32))
    return out


def _split_merged_blobs(mask: np.ndarray, paper: PaperFrame) -> np.ndarray:
    """相邻碎片被粘成一块时，用分水岭拆开"""
    out = mask.copy()
    max_single_px = 22.0 * (paper.px_per_cm ** 2)  # 单块最大约 P4≈24cm²，略留余量
    cnts, _ = cv2.findContours(out, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in cnts:
        area = cv2.contourArea(cnt)
        if area < max_single_px * 0.65:
            continue
        sub = np.zeros_like(out)
        cv2.drawContours(sub, [cnt], -1, 255, thickness=-1)
        n_parts = max(2, min(4, int(round(area / max_single_px))))
        split = _watershed_split_blob(sub, n_expected=n_parts)
        if cv2.countNonZero(split) > 0 and split.shape == sub.shape:
            out[sub > 0] = 0
            out |= split
    return out


def _merge_stacked_paper_frame(gray: np.ndarray) -> Optional[np.ndarray]:
    """上下两块黑区（被白线分开）合并为完整外框"""
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(blur, config.BLACK_PAPER_GRAY_THRESH, 255, cv2.THRESH_BINARY_INV)
    if w >= h and config.CAMERA_CROP_LEFT_FRAC > 0:
        dark[:, : int(w * config.CAMERA_CROP_LEFT_FRAC)] = 0
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_area = h * w
    boxes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.06:
            continue
        x, y, bw, bh = cv2.boundingRect(cnt)
        if not _bbox_aspect_ok(bw, bh) and area < img_area * 0.20:
            continue
        boxes.append((area, x, y, bw, bh))
    if len(boxes) < 2:
        if len(boxes) == 1 and boxes[0][0] >= img_area * config.MAT_MIN_AREA_FRAC:
            _, x, y, bw, bh = boxes[0]
            return np.array(
                [[x, y], [x + bw, y], [x + bw, y + bh], [x, y + bh]],
                dtype=np.float32,
            )
        return None
    boxes.sort(key=lambda b: b[2])
    widths = [b[3] for b in boxes[:2]]
    if abs(widths[0] - widths[1]) > w * 0.18:
        return None
    x0, y0, x1, y1 = _tighten_merge_bounds(boxes, w, h)
    merged_w, merged_h = x1 - x0, y1 - y0
    if not _bbox_aspect_ok(merged_w, merged_h):
        return None
    return np.array(
        [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
        dtype=np.float32,
    )


def _paper_px_per_cm(corners: np.ndarray, landscape_in_image: bool = False) -> float:
    width_px = float(np.linalg.norm(corners[1] - corners[0]))
    height_px = float(np.linalg.norm(corners[3] - corners[0]))
    if landscape_in_image:
        return max(width_px / config.A4_HEIGHT_CM, height_px / config.A4_WIDTH_CM)
    return max(width_px / config.A4_WIDTH_CM, height_px / config.A4_HEIGHT_CM)


def _is_live_camera_frame(paper: PaperFrame, shape: Tuple[int, ...]) -> bool:
    """实拍：低分辨率且纸框贴近画面边缘"""
    h, w = shape[:2]
    if h > 720:
        return False
    pts = paper.corners_px
    margin = 25.0
    return (
        float(pts[:, 0].min()) <= margin
        or float(pts[:, 1].min()) <= margin
        or float(pts[:, 0].max()) >= w - margin
        or float(pts[:, 1].max()) >= h - margin
    )


def resize_for_live_detect(frame: np.ndarray, max_width: int) -> Tuple[np.ndarray, float]:
    """缩略图检测；返回 (小图, scale=小图宽/原图宽)"""
    if max_width <= 0:
        return frame, 1.0
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame, 1.0
    scale = max_width / w
    small = cv2.resize(frame, (max_width, int(h * scale)), interpolation=cv2.INTER_AREA)
    return small, scale


def upscale_overlay(overlay: np.ndarray, target_shape: Tuple[int, ...]) -> np.ndarray:
    th, tw = target_shape[:2]
    oh, ow = overlay.shape[:2]
    if oh == th and ow == tw:
        return overlay
    return cv2.resize(overlay, (tw, th), interpolation=cv2.INTER_LINEAR)


def segment_pieces(
    frame: np.ndarray,
    paper: PaperFrame,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]],
    divider_y_cm: float | None = None,
    *,
    live: bool = False,
) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for low, high in hsv_ranges:
        mask |= cv2.inRange(hsv, np.array(low), np.array(high))

    roi = _inner_roi_mask(paper, frame.shape)
    mask = cv2.bitwise_and(mask, roi)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    # 不做 close，避免相邻白片被桥接；ROI 已裁掉框外，不再清整幅图边缘

    if not live:
        mask = _split_merged_blobs(mask, paper)
    return mask


def _is_divider_contour(bbox_cm: Tuple[float, float, float, float]) -> bool:
    """过滤细长的白色分界线误检"""
    _, _, bw, bh = bbox_cm
    h = max(abs(bh), 0.01)
    w = max(abs(bw), 0.01)
    if w / h > 12 and h < 1.0:
        return True
    if h / w > 12 and w < 1.0:
        return True
    return False


def _contour_to_piece(
    cnt: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    frame_shape: Tuple[int, ...],
) -> Optional[DetectedPiece]:
    area_px = cv2.contourArea(cnt)
    if area_px < 200:
        return None
    area_cm2 = area_px / (paper.px_per_cm ** 2)
    if area_cm2 < config.MIN_PIECE_AREA_CM2 or area_cm2 > config.MAX_PIECE_AREA_SOFT_CM2:
        return None

    rect = cv2.minAreaRect(cnt)
    (cx_px, cy_px), (_w_px, _h_px), angle = rect
    center_cm = _px_to_cm(np.array([cx_px, cy_px]), paper)

    peri = cv2.arcLength(cnt, True)
    approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
    if len(approx) < 3:
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
    if len(approx) >= 3:
        vertices_cm = _contour_to_cm(approx, paper)
    else:
        contour_cm = _contour_to_cm(cnt, paper)
        vertices_cm = resample_polygon(contour_cm, 32)

    x, y, bw, bh = cv2.boundingRect(cnt)
    tl = _px_to_cm(np.array([x, y]), paper)
    br = _px_to_cm(np.array([x + bw, y + bh]), paper)
    bbox_cm = (tl[0], tl[1], br[0] - tl[0], br[1] - tl[1])

    if _is_divider_contour(bbox_cm):
        return None
    if not _point_in_paper_roi((cx_px, cy_px), paper, frame_shape):
        return None

    return DetectedPiece(
        contour=cnt,
        center_cm=center_cm,
        angle_deg=float(angle),
        area_cm2=float(area_cm2),
        vertices_cm=vertices_cm,
        bbox_cm=bbox_cm,
        in_upper_half=center_cm[1] < divider_y_cm,
    )


def detect_pieces(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]],
    *,
    live: bool = False,
) -> List[DetectedPiece]:
    mask = segment_pieces(frame, paper, hsv_ranges, divider_y_cm=divider_y_cm, live=live)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pieces: List[DetectedPiece] = []

    for cnt in contours:
        area_px = cv2.contourArea(cnt)
        if area_px < 200:
            continue
        area_cm2 = area_px / (paper.px_per_cm ** 2)

        if _is_glare_contour(cnt, frame):
            for sub_cnt in _decompose_glare_mixed_blob(cnt, frame, paper):
                piece = _contour_to_piece(sub_cnt, paper, divider_y_cm, frame.shape)
                if piece is not None:
                    pieces.append(piece)
            continue

        if area_cm2 > config.MAX_PIECE_AREA_CM2:
            split_cnts = _split_oversized_contour(cnt, frame.shape, paper)
            if len(split_cnts) < 2:
                split_cnts = _decompose_glare_mixed_blob(cnt, frame, paper)
            if len(split_cnts) >= 1:
                for sub_cnt in split_cnts:
                    if _is_glare_contour(sub_cnt, frame):
                        continue
                    piece = _contour_to_piece(sub_cnt, paper, divider_y_cm, frame.shape)
                    if piece is not None:
                        pieces.append(piece)
                continue
            if area_cm2 > config.MAX_PIECE_AREA_SOFT_CM2:
                continue

        piece = _contour_to_piece(cnt, paper, divider_y_cm, frame.shape)
        if piece is not None:
            pieces.append(piece)
    return pieces


def draw_overlay_live(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    pieces: List[DetectedPiece],
    target_origin: Tuple[float, float],
    *,
    all_pieces: Optional[List[DetectedPiece]] = None,
) -> np.ndarray:
    """实时预览：轻量绘制；可显示框外/下半区碎片（灰色）便于调试"""
    out = frame.copy()
    cv2.polylines(out, [paper.corners_px.astype(np.int32)], True, (0, 255, 255), 2)

    y_px = _divider_y_px(paper, divider_y_cm)
    cv2.line(
        out,
        (int(paper.corners_px[0, 0]), y_px),
        (int(paper.corners_px[1, 0]), y_px),
        (255, 128, 0),
        2,
    )

    ox, oy = target_origin
    target_pts_cm = np.array(
        [
            [ox, oy],
            [ox + config.TARGET_WIDTH_CM, oy],
            [ox + config.TARGET_WIDTH_CM, oy + config.TARGET_HEIGHT_CM],
            [ox, oy + config.TARGET_HEIGHT_CM],
        ]
    )
    target_px = [_cm_to_px(pt, paper) for pt in target_pts_cm]
    cv2.polylines(out, [np.array(target_px, dtype=np.int32)], True, (0, 255, 0), 1)

    upper_ids = {id(p) for p in pieces}
    show = all_pieces if all_pieces is not None else pieces
    upper_idx = 0
    for piece in show:
        is_upper = id(piece) in upper_ids
        if is_upper:
            color = (0, 255, 255)
            label = f"#{upper_idx}"
            upper_idx += 1
        else:
            color = (160, 160, 160)
            label = "L"
        x, y, bw, bh = piece.bbox_cm
        tl = _cm_to_px((x, y), paper)
        br = _cm_to_px((x + bw, y + bh), paper)
        cv2.rectangle(
            out,
            (int(tl[0]), int(tl[1])),
            (int(br[0]), int(br[1])),
            color,
            1 if not is_upper else 2,
        )
        cx, cy = piece.center_cm
        px = _cm_to_px((cx, cy), paper)
        cv2.putText(out, label, (int(px[0]), int(px[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    return out


def draw_overlay(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    pieces: List[DetectedPiece],
    target_origin: Tuple[float, float],
    assignments: Optional[List] = None,
) -> np.ndarray:
    out = frame.copy()
    cv2.polylines(out, [paper.corners_px.astype(np.int32)], True, (0, 255, 255), 2)

    # 分界线
    y_px = int(paper.corners_px[0, 1] + (divider_y_cm / config.A4_HEIGHT_CM) * (paper.corners_px[3, 1] - paper.corners_px[0, 1]))
    cv2.line(
        out,
        (int(paper.corners_px[0, 0]), y_px),
        (int(paper.corners_px[1, 0]), y_px),
        (255, 0, 0),
        2,
    )

    # 目标矩形
    ox, oy = target_origin
    target_pts_cm = np.array(
        [
            [ox, oy],
            [ox + config.TARGET_WIDTH_CM, oy],
            [ox + config.TARGET_WIDTH_CM, oy + config.TARGET_HEIGHT_CM],
            [ox, oy + config.TARGET_HEIGHT_CM],
        ]
    )
    target_px = []
    for pt in target_pts_cm:
        px = _cm_to_px(pt, paper)
        target_px.append(px)
    cv2.polylines(out, [np.array(target_px, dtype=np.int32)], True, (0, 255, 0), 2)

    for i, piece in enumerate(pieces):
        if piece.in_upper_half:
            color = (0, 255, 255)  # 黄框，黑底上更清晰
        else:
            color = (255, 128, 0)
        cv2.drawContours(out, [piece.contour], -1, color, 2)
        cx, cy = piece.center_cm
        px = _cm_to_px((cx, cy), paper)
        cv2.putText(out, f"#{i}", (int(px[0]), int(px[1])), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    if assignments:
        for asg in assignments:
            if len(asg.target_vertices_cm) == 0:
                continue
            ghost = []
            for vx, vy in asg.target_vertices_cm:
                px = _cm_to_px((float(vx), float(vy)), paper)
                ghost.append([int(px[0]), int(px[1])])
            cv2.polylines(out, [np.array(ghost, dtype=np.int32)], True, (0, 200, 0), 1, cv2.LINE_AA)
    return out


def cm_to_px(pt_cm: Tuple[float, float], paper: PaperFrame) -> Tuple[float, float]:
    return _cm_to_px(pt_cm, paper)


def _cm_to_px(pt_cm: Tuple[float, float], paper: PaperFrame) -> Tuple[float, float]:
    px_plane_x, px_plane_y = _cm_to_plane(pt_cm[0], pt_cm[1], paper.landscape_in_image)
    src = _a4_cm_plane_corners(paper.landscape_in_image)
    M = cv2.getPerspectiveTransform(src, paper.corners_px.astype(np.float32))
    pt = np.array([[[px_plane_x, px_plane_y]]], dtype=np.float32)
    out = cv2.perspectiveTransform(pt, M)[0, 0]
    return float(out[0]), float(out[1])
