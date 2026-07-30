"""
仿真动画：真实搬运效果

- 从原图抠出碎片纹理，按顶点仿射变换刚性搬运（形状不变、不翻转）
- 一次只搬一块，已放好的保持不动
- 搬走后原位置留白，不会瞬间拼合
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Tuple

import cv2
import numpy as np

from . import config
from .geometry import (
    apply_rigid_pose,
    decompose_rigid_motion,
    procrustes_rotation_no_flip,
)
from .motion import MotionStep, Phase
from .puzzle_solver import PieceAssignment
from .vision import DetectedPiece, PaperFrame, cm_to_px


class PieceState(Enum):
    WAITING = auto()
    MOVING = auto()
    PLACED = auto()


@dataclass
class PieceVisual:
    index: int
    patch: np.ndarray
    mask: np.ndarray
    x0: int
    y0: int
    src_vertices_cm: np.ndarray
    src_vertices_px: np.ndarray
    start_center: Tuple[float, float]
    end_center: Tuple[float, float]
    end_angle: float
    state: PieceState = PieceState.WAITING
    progress: float = 0.0


def _make_clean_background(frame: np.ndarray, pieces: List[DetectedPiece]) -> np.ndarray:
    bg = frame.copy()
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    for piece in pieces:
        cv2.drawContours(mask, [piece.contour], -1, 255, thickness=-1)
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8), iterations=2)
    bg[mask > 0] = (0, 0, 0)
    return bg


def _extract_piece_patch(
    frame: np.ndarray, contour: np.ndarray
) -> Tuple[np.ndarray, np.ndarray, int, int]:
    mask_full = np.zeros(frame.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask_full, [contour], -1, 255, thickness=-1)
    x, y, w, h = cv2.boundingRect(contour)
    pad = 4
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(frame.shape[1], x + w + pad)
    y1 = min(frame.shape[0], y + h + pad)
    patch = frame[y0:y1, x0:x1].copy()
    mask = mask_full[y0:y1, x0:x1].copy()
    return patch, mask, x0, y0


def _estimate_affine(src: np.ndarray, dst: np.ndarray) -> np.ndarray | None:
    """由对应点估计刚性仿射矩阵（旋转+平移，不缩放）"""
    if len(src) < 3:
        return None
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    if len(src) == 3:
        return cv2.getAffineTransform(src.astype(np.float32), dst.astype(np.float32))
    sc = src.mean(axis=0)
    dc = dst.mean(axis=0)
    R = procrustes_rotation_no_flip(src - sc, dst - dc)
    t = dc - sc @ R.T
    return np.array(
        [[R[0, 0], R[0, 1], t[0]], [R[1, 0], R[1, 1], t[1]]],
        dtype=np.float64,
    )


def _paste_piece_texture(
    canvas: np.ndarray,
    visual: PieceVisual,
    paper: PaperFrame,
    highlight: bool = False,
) -> None:
    t = float(np.clip(visual.progress, 0.0, 1.0))
    sc = np.array(visual.start_center, dtype=np.float64)
    ec = np.array(visual.end_center, dtype=np.float64)
    center = (
        sc[0] + t * (ec[0] - sc[0]),
        sc[1] + t * (ec[1] - sc[1]),
    )
    local = np.asarray(visual.src_vertices_cm, dtype=np.float64) - sc
    curr_v = apply_rigid_pose(local, center, visual.end_angle * t)
    dst_px = np.array([cm_to_px((float(p[0]), float(p[1])), paper) for p in curr_v], dtype=np.float32)
    src_local = np.asarray(visual.src_vertices_px, dtype=np.float64) - np.array(
        [visual.x0, visual.y0], dtype=np.float64
    )

    M = _estimate_affine(src_local, dst_px)
    if M is None:
        return

    border = (0, 0, 0)
    warped = cv2.warpAffine(
        visual.patch,
        M,
        (canvas.shape[1], canvas.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border,
    )
    warped_mask = cv2.warpAffine(
        visual.mask,
        M,
        (canvas.shape[1], canvas.shape[0]),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )

    if highlight:
        tint = warped.astype(np.float32)
        tint[:, :, 0] = np.minimum(tint[:, :, 0] * 0.6 + 80, 255)
        tint[:, :, 1] = np.minimum(tint[:, :, 1] * 0.6 + 200, 255)
        tint[:, :, 2] = np.minimum(tint[:, :, 2] * 0.6 + 200, 255)
        warped = tint.astype(np.uint8)

    idx = warped_mask > 0
    canvas[idx] = warped[idx]
    cv2.drawContours(canvas, [_largest_contour(warped_mask)], -1, (0, 0, 0), 1)


def _largest_contour(mask: np.ndarray) -> np.ndarray:
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return np.zeros((0, 1, 2), dtype=np.int32)
    c = max(cnts, key=cv2.contourArea)
    return c


def _draw_target_hint(
    canvas: np.ndarray,
    paper: PaperFrame,
    target_origin: Tuple[float, float],
    target_size: Tuple[float, float] | None = None,
) -> None:
    ox, oy = target_origin
    tw = target_size[0] if target_size else config.TARGET_WIDTH_CM
    th = target_size[1] if target_size else config.TARGET_HEIGHT_CM
    pts = []
    for x, y in [
        (ox, oy),
        (ox + tw, oy),
        (ox + tw, oy + th),
        (ox, oy + th),
    ]:
        px = cm_to_px((x, y), paper)
        pts.append([int(px[0]), int(px[1])])
    cv2.polylines(canvas, [np.array(pts, dtype=np.int32)], True, (0, 180, 0), 1, cv2.LINE_AA)


def _draw_divider(canvas: np.ndarray, paper: PaperFrame, divider_y_cm: float) -> None:
    y_px = int(
        paper.corners_px[0, 1]
        + (divider_y_cm / config.A4_HEIGHT_CM)
        * (paper.corners_px[3, 1] - paper.corners_px[0, 1])
    )
    cv2.line(
        canvas,
        (int(paper.corners_px[0, 0]), y_px),
        (int(paper.corners_px[1, 0]), y_px),
        (255, 0, 0),
        2,
    )


def _render_scene(
    background: np.ndarray,
    paper: PaperFrame,
    visuals: List[PieceVisual],
    divider_y_cm: float,
    target_origin: Tuple[float, float],
    target_size: Tuple[float, float] | None,
    active_index: int | None,
    step: MotionStep | None,
    step_index: int,
    total_steps: int,
    progress: float,
) -> np.ndarray:
    canvas = background.copy()
    _draw_target_hint(canvas, paper, target_origin, target_size)
    _draw_divider(canvas, paper, divider_y_cm)

    order = []
    for v in visuals:
        if v.state == PieceState.PLACED:
            order.append(v)
    for v in visuals:
        if v.state == PieceState.WAITING:
            order.append(v)
    for v in visuals:
        if v.index == active_index and v.state == PieceState.MOVING:
            order.append(v)

    for v in order:
        _paste_piece_texture(canvas, v, paper, highlight=(v.index == active_index))

    bar_h = 70
    bar = np.full((bar_h, canvas.shape[1], 3), 240, dtype=np.uint8)
    desc = step.description if step else "Done"
    cv2.putText(
        bar,
        f"Step {step_index + 1}/{total_steps}  {desc}",
        (12, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (30, 30, 30),
        2,
    )
    cv2.putText(
        bar,
        "Sim: rigid motion, one piece at a time",
        (12, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (80, 80, 80),
        1,
    )
    cv2.rectangle(
        bar,
        (12, 56),
        (12 + int((canvas.shape[1] - 24) * progress), 64),
        (0, 160, 0),
        -1,
    )
    cv2.rectangle(bar, (12, 56), (canvas.shape[1] - 12, 64), (120, 120, 120), 1)
    return np.vstack([canvas, bar])


def _build_visuals(
    base_frame: np.ndarray,
    paper: PaperFrame,
    pieces: List[DetectedPiece],
    steps: List[MotionStep],
) -> Dict[int, PieceVisual]:
    step_map = {s.piece_index: s for s in steps if s.phase == Phase.ASSEMBLE}
    visuals: Dict[int, PieceVisual] = {}

    for i, piece in enumerate(pieces):
        step = step_map.get(i)
        if step is None:
            continue
        patch, mask, x0, y0 = _extract_piece_patch(base_frame, piece.contour)

        src_v = np.asarray(piece.vertices_cm, dtype=np.float64).reshape(-1, 2)
        tgt_v = np.asarray(step.to_vertices_cm, dtype=np.float64).reshape(-1, 2)
        if len(src_v) < 3 or len(tgt_v) < 3:
            continue

        _, start_c, end_c, end_angle = decompose_rigid_motion(src_v, tgt_v)
        src_px = np.array(
            [cm_to_px((float(p[0]), float(p[1])), paper) for p in src_v],
            dtype=np.float64,
        )
        visuals[i] = PieceVisual(
            index=i,
            patch=patch,
            mask=mask,
            x0=x0,
            y0=y0,
            src_vertices_cm=src_v,
            src_vertices_px=src_px,
            start_center=start_c,
            end_center=end_c,
            end_angle=end_angle,
        )
    return visuals


def play_motion_animation(
    base_frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    pieces: List[DetectedPiece],
    steps: List[MotionStep],
    assignments: List[PieceAssignment],
    target_origin: Tuple[float, float] | None = None,
    target_size: Tuple[float, float] | None = None,
    frames_per_step: int = 50,
    pause_ms: int = 20,
    window_name: str = "Puzzle Simulation",
) -> None:
    if target_origin is None:
        target_origin = (config.TARGET_ORIGIN_X_CM, config.TARGET_ORIGIN_Y_CM)

    background = _make_clean_background(base_frame, pieces)
    visuals = _build_visuals(base_frame, paper, pieces, steps)
    motion_steps = [s for s in steps if s.phase != Phase.DONE]
    total = len(motion_steps)
    paused = False

    def show(step: MotionStep | None, idx: int, prog: float, active: int | None) -> None:
        frame = _render_scene(
            background,
            paper,
            list(visuals.values()),
            divider_y_cm,
            target_origin,
            target_size,
            active,
            step,
            idx,
            total,
            prog,
        )
        cv2.imshow(window_name, cv2.resize(frame, None, fx=config.DISPLAY_SCALE, fy=config.DISPLAY_SCALE))

    show(motion_steps[0] if motion_steps else None, 0, 0.0, None)
    cv2.waitKey(1000)

    for step_idx, step in enumerate(motion_steps):
        vi = visuals.get(step.piece_index)
        if vi is None:
            continue
        vi.state = PieceState.MOVING

        for f in range(frames_per_step + 1):
            t = f / frames_per_step
            t_smooth = t * t * (3 - 2 * t)
            vi.progress = t_smooth

            show(step, step_idx, (step_idx + t) / max(total, 1), step.piece_index)

            key = cv2.waitKey(0 if paused else pause_ms) & 0xFF
            if key in (ord("q"), 27):
                cv2.destroyWindow(window_name)
                return
            if key == ord(" "):
                paused = not paused

        vi.progress = 1.0
        vi.state = PieceState.PLACED

    final = _render_scene(
        background,
        paper,
        list(visuals.values()),
        divider_y_cm,
        target_origin,
        target_size,
        None,
        None,
        total - 1 if total else 0,
        total,
        1.0,
    )
    n_done = len([v for v in visuals.values() if v.state == PieceState.PLACED])
    cv2.putText(
        final,
        f"Done - {n_done} pieces placed",
        (12, final.shape[0] - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.58,
        (0, 120, 0),
        2,
    )
    cv2.imshow(window_name, cv2.resize(final, None, fx=config.DISPLAY_SCALE, fy=config.DISPLAY_SCALE))
    cv2.waitKey(0)
    cv2.destroyWindow(window_name)
