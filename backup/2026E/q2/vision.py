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


def _find_paper_frame_from_content(gray: np.ndarray, thresh: int = 15) -> Optional[np.ndarray]:
    """
    黑底场景：从灰边/白线/白片等内容推断 A4 内框。
    合成图与实拍（黑纸上有白线、白片）均适用。
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

    ratio = _a4_aspect_ratio(width, height)
    expected = config.A4_WIDTH_CM / config.A4_HEIGHT_CM
    if abs(ratio - expected) > 0.12:
        return None

    return np.array(
        [[left, top], [right, top], [right, bottom], [left, bottom]],
        dtype=np.float32,
    )


def _contour_touches_image_border(pts: np.ndarray, w: int, h: int, margin: int = 8) -> bool:
    x_min, y_min = pts.min(axis=0)
    x_max, y_max = pts.max(axis=0)
    return (
        x_min <= margin
        or y_min <= margin
        or x_max >= w - margin
        or y_max >= h - margin
    )


def _detect_paper_dark(frame: np.ndarray) -> Optional[PaperFrame]:
    """黑底场景：检测 A4 纸外轮廓"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = frame.shape[:2]

    content_frame = _find_paper_frame_from_content(gray)
    if content_frame is not None:
        ordered = _order_corners(content_frame)
        height_px = np.linalg.norm(ordered[3] - ordered[0])
        px_per_cm = height_px / config.A4_HEIGHT_CM
        return PaperFrame(corners_px=ordered, px_per_cm=px_per_cm)

    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(blur, config.BLACK_PAPER_GRAY_THRESH, 255, cv2.THRESH_BINARY_INV)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    img_area = h * w
    best = None
    best_score = 0.0

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < img_area * 0.08:
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
        if _contour_touches_image_border(pts, w, h):
            continue
        if area > best_score:
            best_score = area
            best = pts

    if best is None:
        content_frame = _find_paper_frame_from_content(gray, thresh=8)
        if content_frame is not None:
            best = content_frame
        else:
            margin = 20
            best = np.array(
                [[margin, margin], [w - margin, margin], [w - margin, h - margin], [margin, h - margin]],
                dtype=np.float32,
            )

    ordered = _order_corners(best)
    height_px = np.linalg.norm(ordered[3] - ordered[0])
    px_per_cm = height_px / config.A4_HEIGHT_CM
    return PaperFrame(corners_px=ordered, px_per_cm=px_per_cm)


def _px_to_cm(pt_px: np.ndarray, paper: PaperFrame) -> Tuple[float, float]:
    """透视近似：用仿射变换将像素映射到 cm"""
    dst = np.array(
        [
            [0, 0],
            [config.A4_WIDTH_CM, 0],
            [config.A4_WIDTH_CM, config.A4_HEIGHT_CM],
            [0, config.A4_HEIGHT_CM],
        ],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(paper.corners_px.astype(np.float32), dst)
    pt = np.array([[[pt_px[0], pt_px[1]]]], dtype=np.float32)
    out = cv2.perspectiveTransform(pt, M)[0, 0]
    return float(out[0]), float(out[1])


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


def segment_pieces(
    frame: np.ndarray,
    paper: PaperFrame,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]],
    divider_y_cm: float | None = None,
) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for low, high in hsv_ranges:
        mask |= cv2.inRange(hsv, np.array(low), np.array(high))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 去掉贴边噪声（A4 边框）
    border = max(3, int(paper.px_per_cm * 0.3))
    mask[:border, :] = 0
    mask[-border:, :] = 0
    mask[:, :border] = 0
    mask[:, -border:] = 0

    # 去掉白色分界线区域，避免被当成碎片
    if divider_y_cm is not None:
        band = max(2, int(paper.px_per_cm * 0.35))
        y_px = int(
            paper.corners_px[0, 1]
            + (divider_y_cm / config.A4_HEIGHT_CM)
            * (paper.corners_px[3, 1] - paper.corners_px[0, 1])
        )
        mask[max(0, y_px - band) : y_px + band, :] = 0

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


def detect_pieces(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    hsv_ranges: Sequence[Tuple[Tuple[int, int, int], Tuple[int, int, int]]],
) -> List[DetectedPiece]:
    mask = segment_pieces(frame, paper, hsv_ranges, divider_y_cm=divider_y_cm)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pieces: List[DetectedPiece] = []

    for cnt in contours:
        area_px = cv2.contourArea(cnt)
        if area_px < 200:
            continue
        area_cm2 = area_px / (paper.px_per_cm ** 2)
        if area_cm2 < config.MIN_PIECE_AREA_CM2 or area_cm2 > config.MAX_PIECE_AREA_CM2:
            continue

        rect = cv2.minAreaRect(cnt)
        (cx_px, cy_px), (w_px, h_px), angle = rect
        center_cm = _px_to_cm(np.array([cx_px, cy_px]), paper)

        peri = cv2.arcLength(cnt, True)
        contour_cm = _contour_to_cm(cnt, paper)
        approx = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(approx) < 3:
            approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) >= 3:
            vertices_cm = _contour_to_cm(approx, paper)
        else:
            vertices_cm = resample_polygon(contour_cm, 32)

        x, y, bw, bh = cv2.boundingRect(cnt)
        tl = _px_to_cm(np.array([x, y]), paper)
        br = _px_to_cm(np.array([x + bw, y + bh]), paper)
        bbox_cm = (tl[0], tl[1], br[0] - tl[0], br[1] - tl[1])

        if _is_divider_contour(bbox_cm):
            continue

        in_upper = center_cm[1] < divider_y_cm
        pieces.append(
            DetectedPiece(
                contour=cnt,
                center_cm=center_cm,
                angle_deg=float(angle),
                area_cm2=float(area_cm2),
                vertices_cm=vertices_cm,
                bbox_cm=bbox_cm,
                in_upper_half=in_upper,
            )
        )
    return pieces


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
    src = np.array(
        [
            [0, 0],
            [config.A4_WIDTH_CM, 0],
            [config.A4_WIDTH_CM, config.A4_HEIGHT_CM],
            [0, config.A4_HEIGHT_CM],
        ],
        dtype=np.float32,
    )
    M = cv2.getPerspectiveTransform(
        src, paper.corners_px.astype(np.float32)
    )
    pt = np.array([[[pt_cm[0], pt_cm[1]]]], dtype=np.float32)
    out = cv2.perspectiveTransform(pt, M)[0, 0]
    return float(out[0]), float(out[1])
