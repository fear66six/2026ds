"""第二问：碎片多边形分析（≤5 顶点，边长 ≥2cm）"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

import cv2
import numpy as np

from .vision import DetectedPiece, PaperFrame

from . import config


@dataclass
class EdgeInfo:
    index: int
    length_cm: float
    angle_deg: float
    p0: Tuple[float, float]
    p1: Tuple[float, float]


@dataclass
class AnalyzedPiece:
    index: int
    source: DetectedPiece
    vertices_cm: np.ndarray
    area_cm2: float
    edges: List[EdgeInfo] = field(default_factory=list)


def _polygon_area(vertices: np.ndarray) -> float:
    pts = vertices.reshape(-1, 2)
    x, y = pts[:, 0], pts[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def simplify_polygon(vertices_cm: np.ndarray, max_vertices: int = 5) -> np.ndarray:
    pts = np.asarray(vertices_cm, dtype=np.float64).reshape(-1, 2)
    if len(pts) <= max_vertices:
        return pts.copy()

    peri = cv2.arcLength(pts.astype(np.float32).reshape(-1, 1, 2), True)
    for eps_ratio in (0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.12, 0.15):
        approx = cv2.approxPolyDP(
            pts.astype(np.float32).reshape(-1, 1, 2),
            eps_ratio * peri,
            True,
        )
        if 3 <= len(approx) <= max_vertices:
            return approx.reshape(-1, 2).astype(np.float64)

    approx = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), 0.15 * peri, True)
    if len(approx) < 3:
        return pts[:3].copy()
    if len(approx) > max_vertices:
        approx = cv2.approxPolyDP(pts.astype(np.float32).reshape(-1, 1, 2), 0.20 * peri, True)
    return approx.reshape(-1, 2).astype(np.float64)


def _extract_edges(vertices_cm: np.ndarray) -> List[EdgeInfo]:
    pts = np.asarray(vertices_cm, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    edges: List[EdgeInfo] = []
    for i in range(n):
        p0 = pts[i]
        p1 = pts[(i + 1) % n]
        d = p1 - p0
        length = float(np.linalg.norm(d))
        angle = float(np.degrees(np.arctan2(d[1], d[0])))
        edges.append(EdgeInfo(i, length, angle, (float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1]))))
    return edges


def _merge_short_edges(vertices_cm: np.ndarray, min_edge: float) -> np.ndarray:
    """合并过短边（检测噪声导致），保持多边形有效"""
    pts = np.asarray(vertices_cm, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 3:
        return pts

    changed = True
    while changed and len(pts) >= 3:
        changed = False
        n = len(pts)
        new_pts = []
        i = 0
        while i < n:
            p0 = pts[i]
            p1 = pts[(i + 1) % n]
            el = float(np.linalg.norm(p1 - p0))
            if el < min_edge and n > 3:
                changed = True
                i += 1
                continue
            new_pts.append(p0)
            i += 1
        if new_pts:
            pts = np.array(new_pts, dtype=np.float64)
    return pts


def analyze_pieces(detected: List[DetectedPiece]) -> List[AnalyzedPiece]:
    out: List[AnalyzedPiece] = []
    for i, piece in enumerate(detected):
        raw = np.asarray(piece.vertices_cm, dtype=np.float64).reshape(-1, 2)
        if len(raw) <= config.MAX_VERTICES:
            verts = _merge_short_edges(raw, config.MIN_EDGE_CM * 0.45)
        else:
            verts = simplify_polygon(raw, config.MAX_VERTICES)
            verts = _merge_short_edges(verts, config.MIN_EDGE_CM * 0.5)
        if len(verts) > config.MAX_VERTICES:
            verts = simplify_polygon(verts, config.MAX_VERTICES)
        area = max(_polygon_area(verts), float(piece.area_cm2) * 0.92)
        edges = _extract_edges(verts)
        if any(e.length_cm < config.MIN_EDGE_CM * 0.85 for e in edges):
            if len(raw) <= config.MAX_VERTICES:
                verts = _merge_short_edges(raw, config.MIN_EDGE_CM * 0.35)
                edges = _extract_edges(verts)
            else:
                verts = simplify_polygon(raw, config.MAX_VERTICES)
                edges = _extract_edges(verts)
            if any(e.length_cm < config.MIN_EDGE_CM * 0.85 for e in edges):
                continue
        if float(piece.area_cm2) < config.MIN_PIECE_AREA_CM2 or area > config.MAX_PIECE_AREA_CM2:
            continue
        out.append(
            AnalyzedPiece(
                index=i,
                source=piece,
                vertices_cm=verts,
                area_cm2=area,
                edges=edges,
            )
        )
    return out


def cm_to_px(pt_cm: Tuple[float, float], paper: PaperFrame) -> Tuple[float, float]:
    from .vision import cm_to_px as _cm_to_px

    return _cm_to_px(pt_cm, paper)
