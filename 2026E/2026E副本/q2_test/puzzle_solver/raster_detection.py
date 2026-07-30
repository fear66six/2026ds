"""Standalone raster-to-polygon detection for Q2-style board images.

The geometric solver does not need this module.  It is used only by the
optional local-image adapter and intentionally contains no template matching,
camera control, or robot-specific code.  Coordinates in this module use
centimetres to match the A4 calibration; ``image_input`` converts the final
vertices to the solver's millimetre unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np


A4_WIDTH_CM = 21.0
A4_HEIGHT_CM = 29.7
DIVIDER_Y_CM = A4_HEIGHT_CM / 2.0
DEFAULT_HSV_RANGES = (((0, 0, 120), (180, 100, 255)),)
WHITE_DIVIDER_GRAY_THRESHOLD = 160
BLACK_PAPER_GRAY_THRESHOLD = 90
MAX_PIECES = 4
MAX_VERTICES = 5
MIN_PIECE_AREA_CM2 = 3.0
MAX_PIECE_AREA_CM2 = 80.0
MIN_DETECTED_AREA_CM2 = 1.0
MAX_DETECTED_AREA_CM2 = 55.0
MIN_PHYSICAL_EDGE_CM = 2.0
MERGE_SHORT_EDGE_CM = 1.0


@dataclass(frozen=True)
class PaperFrame:
    """Detected A4 paper quadrilateral and approximate image scale."""

    corners_px: np.ndarray
    px_per_cm: float


@dataclass(frozen=True)
class DetectedPiece:
    """One segmented raster contour in calibrated board coordinates."""

    contour: np.ndarray
    center_cm: tuple[float, float]
    angle_deg: float
    area_cm2: float
    vertices_cm: np.ndarray
    bbox_cm: tuple[float, float, float, float]
    in_upper_half: bool


@dataclass(frozen=True)
class AnalyzedPiece:
    """A detected contour simplified to three through five vertices."""

    index: int
    vertices_cm: np.ndarray


def _order_corners(points: np.ndarray) -> np.ndarray:
    ordered = np.zeros((4, 2), dtype=np.float32)
    coordinate_sum = points.sum(axis=1)
    ordered[0] = points[np.argmin(coordinate_sum)]
    ordered[2] = points[np.argmax(coordinate_sum)]
    coordinate_difference = np.diff(points, axis=1)
    ordered[1] = points[np.argmin(coordinate_difference)]
    ordered[3] = points[np.argmax(coordinate_difference)]
    return ordered


def _find_paper_frame_from_content(
    gray: np.ndarray,
    threshold: int = 15,
) -> np.ndarray | None:
    height, width = gray.shape
    sample_xs = (width // 4, width // 2, 3 * width // 4)
    sample_ys = (height // 4, height // 2, 3 * height // 4)
    tops: list[int] = []
    bottoms: list[int] = []
    lefts: list[int] = []
    rights: list[int] = []

    for x_coordinate in sample_xs:
        for y_coordinate in range(height):
            if gray[y_coordinate, x_coordinate] > threshold:
                tops.append(y_coordinate)
                break
        for y_coordinate in range(height - 1, -1, -1):
            if gray[y_coordinate, x_coordinate] > threshold:
                bottoms.append(y_coordinate)
                break
    for y_coordinate in sample_ys:
        for x_coordinate in range(width):
            if gray[y_coordinate, x_coordinate] > threshold:
                lefts.append(x_coordinate)
                break
        for x_coordinate in range(width - 1, -1, -1):
            if gray[y_coordinate, x_coordinate] > threshold:
                rights.append(x_coordinate)
                break

    if not (tops and bottoms and lefts and rights):
        return None
    top = int(np.median(tops))
    bottom = int(np.median(bottoms))
    left = int(np.median(lefts))
    right = int(np.median(rights))
    paper_width = right - left
    paper_height = bottom - top
    if paper_width < 50 or paper_height < 50:
        return None
    observed_ratio = paper_width / max(paper_height, 1.0)
    if abs(observed_ratio - A4_WIDTH_CM / A4_HEIGHT_CM) > 0.12:
        return None
    return np.asarray(
        ((left, top), (right, top), (right, bottom), (left, bottom)),
        dtype=np.float32,
    )


def _touches_image_border(
    points: np.ndarray,
    width: int,
    height: int,
    margin: int = 8,
) -> bool:
    minimum_x, minimum_y = points.min(axis=0)
    maximum_x, maximum_y = points.max(axis=0)
    return (
        minimum_x <= margin
        or minimum_y <= margin
        or maximum_x >= width - margin
        or maximum_y >= height - margin
    )


def detect_paper(frame: np.ndarray) -> PaperFrame | None:
    """Detect an A4 board in a dark-background image."""

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = frame.shape[:2]
    content_frame = _find_paper_frame_from_content(gray)
    if content_frame is not None:
        ordered = _order_corners(content_frame)
        height_px = float(np.linalg.norm(ordered[3] - ordered[0]))
        return PaperFrame(ordered, height_px / A4_HEIGHT_CM)

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(
        blurred,
        BLACK_PAPER_GRAY_THRESHOLD,
        255,
        cv2.THRESH_BINARY_INV,
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: np.ndarray | None = None
    best_area = 0.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < height * width * 0.08:
            continue
        perimeter = cv2.arcLength(contour, True)
        approximate = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(approximate) > 4:
            approximate = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(approximate) != 4:
            continue
        points = approximate.reshape(-1, 2).astype(np.float32)
        if _touches_image_border(points, width, height):
            continue
        if area > best_area:
            best_area = area
            best = points

    if best is None:
        best = _find_paper_frame_from_content(gray, threshold=8)
    if best is None:
        margin = 20
        best = np.asarray(
            (
                (margin, margin),
                (width - margin, margin),
                (width - margin, height - margin),
                (margin, height - margin),
            ),
            dtype=np.float32,
        )
    ordered = _order_corners(best)
    height_px = float(np.linalg.norm(ordered[3] - ordered[0]))
    return PaperFrame(ordered, height_px / A4_HEIGHT_CM)


def _perspective_matrix(paper: PaperFrame) -> np.ndarray:
    destination = np.asarray(
        ((0, 0), (A4_WIDTH_CM, 0), (A4_WIDTH_CM, A4_HEIGHT_CM), (0, A4_HEIGHT_CM)),
        dtype=np.float32,
    )
    return cv2.getPerspectiveTransform(paper.corners_px.astype(np.float32), destination)


def _point_to_cm(point_px: np.ndarray, paper: PaperFrame) -> tuple[float, float]:
    point = np.asarray([[[point_px[0], point_px[1]]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(point, _perspective_matrix(paper))[0, 0]
    return (float(transformed[0]), float(transformed[1]))


def contour_to_cm(contour: np.ndarray, paper: PaperFrame) -> np.ndarray:
    """Map a pixel contour to calibrated centimetre coordinates."""

    points = np.asarray(contour, dtype=np.float32).reshape(-1, 1, 2)
    transformed = cv2.perspectiveTransform(points, _perspective_matrix(paper))
    return transformed.reshape(-1, 2).astype(np.float64)


def detect_divider_line(frame: np.ndarray, paper: PaperFrame) -> float:
    """Return the horizontal board divider coordinate in centimetres."""

    top_left, top_right, _, bottom_left = paper.corners_px
    middle_y = int(top_left[1] + (bottom_left[1] - top_left[1]) * 0.5)
    left_x = int(top_left[0])
    right_x = int(top_right[0])
    y_start = max(0, middle_y - 40)
    region = frame[y_start : middle_y + 40, left_x:right_x]
    if region.size == 0:
        return DIVIDER_Y_CM
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    _, bright = cv2.threshold(
        gray,
        WHITE_DIVIDER_GRAY_THRESHOLD,
        255,
        cv2.THRESH_BINARY,
    )
    lines = cv2.HoughLinesP(
        bright,
        1,
        np.pi / 180.0,
        40,
        minLineLength=60,
        maxLineGap=15,
    )
    if lines is None:
        return DIVIDER_Y_CM
    best_y: float | None = None
    best_length = 0
    for first_x, first_y, second_x, second_y in lines.reshape(-1, 4):
        if abs(second_y - first_y) > 10:
            continue
        length = abs(second_x - first_x)
        if length > best_length:
            best_length = length
            best_y = (first_y + second_y) / 2.0 + y_start
    if best_y is None:
        return DIVIDER_Y_CM
    return _point_to_cm(np.asarray((left_x, best_y)), paper)[1]


def _resample_polygon(vertices: np.ndarray, count: int = 32) -> np.ndarray:
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 2)
    if len(points) < 3:
        return np.repeat(points, count, axis=0)[:count]
    closed = np.vstack((points, points[0]))
    segment_lengths = np.linalg.norm(np.diff(closed, axis=0), axis=1)
    total_length = float(segment_lengths.sum())
    if total_length <= 1e-9:
        return np.repeat(points[:1], count, axis=0)
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    samples = np.linspace(0.0, total_length, count, endpoint=False)
    output: list[np.ndarray] = []
    segment_index = 0
    for sample in samples:
        while (
            segment_index < len(segment_lengths) - 1
            and cumulative[segment_index + 1] < sample
        ):
            segment_index += 1
        length = segment_lengths[segment_index]
        fraction = (
            (sample - cumulative[segment_index]) / length if length > 1e-9 else 0.0
        )
        output.append(
            closed[segment_index] * (1.0 - fraction)
            + closed[segment_index + 1] * fraction
        )
    return np.asarray(output, dtype=np.float64)


def _segment_piece_mask(
    frame: np.ndarray,
    paper: PaperFrame,
    hsv_ranges: Sequence[tuple[tuple[int, int, int], tuple[int, int, int]]],
) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lower, upper in hsv_ranges:
        mask |= cv2.inRange(hsv, np.asarray(lower), np.asarray(upper))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    border = max(3, int(paper.px_per_cm * 0.35))
    mask[:border, :] = 0
    mask[-border:, :] = 0
    mask[:, :border] = 0
    mask[:, -border:] = 0
    return mask


def _watershed_split_blob(blob: np.ndarray, expected_count: int) -> np.ndarray:
    blob = (blob > 0).astype(np.uint8) * 255
    if not np.any(blob):
        return blob
    distance_transform = cv2.distanceTransform(blob, cv2.DIST_L2, 5)
    peak = float(distance_transform.max())
    if peak < 4.0:
        return blob
    _, foreground = cv2.threshold(
        distance_transform,
        max(2.0, 0.38 * peak),
        255,
        0,
    )
    foreground = np.uint8(foreground)
    unknown = cv2.subtract(blob, foreground)
    _, markers = cv2.connectedComponents(foreground)
    if markers.max() < 2:
        return blob
    markers += 1
    markers[unknown == 255] = 0
    cv2.watershed(cv2.cvtColor(blob, cv2.COLOR_GRAY2BGR), markers)
    output = np.zeros_like(blob)
    accepted = 0
    for label in range(2, int(markers.max()) + 1):
        region = ((markers == label) & (blob > 0)).astype(np.uint8) * 255
        if cv2.countNonZero(region) < 80:
            continue
        output = cv2.bitwise_or(output, region)
        accepted += 1
        if accepted >= expected_count:
            break
    return output if cv2.countNonZero(output) else blob


def _split_large_blobs(mask: np.ndarray, maximum_area_px: float) -> np.ndarray:
    output = mask.copy()
    contours, _ = cv2.findContours(output, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area <= maximum_area_px:
            continue
        blob = np.zeros_like(output)
        cv2.drawContours(blob, [contour], -1, 255, thickness=-1)
        expected_count = min(4, max(2, int(round(area / max(maximum_area_px, 1.0)))))
        eroded = cv2.erode(blob, np.ones((5, 5), np.uint8), iterations=2)
        split = _watershed_split_blob(blob, expected_count)
        if cv2.countNonZero(eroded):
            split = cv2.bitwise_or(split, eroded)
        output[blob > 0] = 0
        output |= split
    return output


def _is_divider_contour(bounds_cm: tuple[float, float, float, float]) -> bool:
    _, _, width, height = bounds_cm
    absolute_width = max(abs(width), 0.01)
    absolute_height = max(abs(height), 0.01)
    return (
        absolute_width / absolute_height > 12.0 and absolute_height < 1.0
    ) or (
        absolute_height / absolute_width > 12.0 and absolute_width < 1.0
    )


def detect_pieces(
    frame: np.ndarray,
    paper: PaperFrame,
    divider_y_cm: float,
    hsv_ranges: Sequence[
        tuple[tuple[int, int, int], tuple[int, int, int]]
    ] = DEFAULT_HSV_RANGES,
) -> list[DetectedPiece]:
    """Segment white upper-board fragments without using external packages."""

    mask = _segment_piece_mask(frame, paper, hsv_ranges)
    maximum_area_px = MAX_DETECTED_AREA_CM2 * paper.px_per_cm**2
    mask = _split_large_blobs(mask, maximum_area_px * 1.15)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask = cv2.dilate(mask, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    pieces: list[DetectedPiece] = []
    for contour in contours:
        area_px = float(cv2.contourArea(contour))
        if area_px < 120:
            continue
        area_cm2 = area_px / paper.px_per_cm**2
        if not MIN_DETECTED_AREA_CM2 <= area_cm2 <= MAX_DETECTED_AREA_CM2:
            continue
        rectangle = cv2.minAreaRect(contour)
        (center_x, center_y), _, angle = rectangle
        center_cm = _point_to_cm(np.asarray((center_x, center_y)), paper)
        perimeter = cv2.arcLength(contour, True)
        approximate = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approximate) < 3:
            approximate = cv2.approxPolyDP(contour, 0.04 * perimeter, True)
        contour_cm = contour_to_cm(contour, paper)
        vertices_cm = (
            contour_to_cm(approximate, paper)
            if len(approximate) >= 3
            else _resample_polygon(contour_cm)
        )
        x_coordinate, y_coordinate, width, height = cv2.boundingRect(contour)
        top_left = _point_to_cm(np.asarray((x_coordinate, y_coordinate)), paper)
        bottom_right = _point_to_cm(
            np.asarray((x_coordinate + width, y_coordinate + height)),
            paper,
        )
        bounds_cm = (
            top_left[0],
            top_left[1],
            bottom_right[0] - top_left[0],
            bottom_right[1] - top_left[1],
        )
        if _is_divider_contour(bounds_cm):
            continue
        pieces.append(
            DetectedPiece(
                contour=contour,
                center_cm=center_cm,
                angle_deg=float(angle),
                area_cm2=float(area_cm2),
                vertices_cm=vertices_cm,
                bbox_cm=bounds_cm,
                in_upper_half=center_cm[1] < divider_y_cm,
            )
        )
    return pieces


def _interior_angle(previous: np.ndarray, current: np.ndarray, following: np.ndarray) -> float:
    first = previous - current
    second = following - current
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-9:
        return 0.0
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def _strip_spurious_vertices(vertices: np.ndarray) -> np.ndarray:
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 2).copy()
    for _ in range(len(points)):
        if len(points) <= 3:
            break
        removable = [
            index
            for index in range(len(points))
            if not 20.0
            <= _interior_angle(points[index - 1], points[index], points[(index + 1) % len(points)])
            <= 158.0
        ]
        if not removable:
            break
        points = np.delete(points, removable[0], axis=0)
    return points


def _merge_short_edges(vertices: np.ndarray) -> np.ndarray:
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 2).copy()
    for _ in range(len(points)):
        if len(points) <= 3:
            break
        lengths = [
            float(np.linalg.norm(points[(index + 1) % len(points)] - points[index]))
            for index in range(len(points))
        ]
        merge_limit = min(
            1.5,
            max(MERGE_SHORT_EDGE_CM, float(np.median(lengths)) * 0.43),
        )
        if min(lengths) >= merge_limit:
            break
        merged = False
        for short_index in sorted(range(len(points)), key=lengths.__getitem__):
            if lengths[short_index] >= merge_limit:
                break
            delete_index = (short_index + 1) % len(points)
            angle = _interior_angle(
                points[short_index],
                points[delete_index],
                points[(delete_index + 1) % len(points)],
            )
            if abs(angle - 90.0) <= 12.0:
                delete_index = short_index
                angle = _interior_angle(
                    points[delete_index - 1],
                    points[delete_index],
                    points[(delete_index + 1) % len(points)],
                )
                if abs(angle - 90.0) <= 12.0:
                    continue
            if len(points) == 4:
                delete_angle = _interior_angle(
                    points[delete_index - 1],
                    points[delete_index],
                    points[(delete_index + 1) % len(points)],
                )
                if not (delete_angle > 160.0 or delete_angle < 20.0):
                    continue
            points = np.delete(points, delete_index, axis=0)
            merged = True
            break
        if not merged:
            break
    return points


def _merge_collinear_vertices(vertices: np.ndarray) -> np.ndarray:
    points = np.asarray(vertices, dtype=np.float64).reshape(-1, 2).copy()
    for _ in range(len(points)):
        if len(points) <= 3:
            break
        merged = False
        for index in range(len(points)):
            angle = _interior_angle(
                points[index - 1], points[index], points[(index + 1) % len(points)]
            )
            if abs(180.0 - angle) <= 12.0:
                points = np.delete(points, index, axis=0)
                merged = True
                break
        if not merged:
            break
    return points


def _try_triangle(
    contour: np.ndarray,
    paper: PaperFrame,
    vertices: np.ndarray,
) -> np.ndarray:
    if len(vertices) <= 3:
        return vertices
    contour_cm = contour_to_cm(contour, paper).astype(np.float32)
    reference_area = float(cv2.contourArea(contour_cm.reshape(-1, 1, 2)))
    if reference_area <= 1e-6:
        return vertices
    perimeter = cv2.arcLength(contour, True)
    best: np.ndarray | None = None
    best_error = float("inf")
    for ratio in (0.08, 0.10, 0.12, 0.15, 0.18, 0.22):
        triangle = cv2.approxPolyDP(contour, ratio * perimeter, True)
        if len(triangle) != 3:
            continue
        candidate = contour_to_cm(triangle, paper)
        candidate_area = float(
            cv2.contourArea(candidate.astype(np.float32).reshape(-1, 1, 2))
        )
        error = abs(candidate_area - reference_area) / reference_area
        if error < best_error:
            best = candidate
            best_error = error
    return best if best is not None and best_error <= 0.08 else vertices


def detect_polygon_vertices(piece: DetectedPiece, paper: PaperFrame) -> np.ndarray:
    """Simplify a raster contour while retaining at most five real corners."""

    perimeter = cv2.arcLength(piece.contour, True)
    approximate: np.ndarray | None = None
    for ratio in (0.025, 0.04, 0.06, 0.08):
        trial = cv2.approxPolyDP(piece.contour, ratio * perimeter, True)
        if len(trial) >= 3:
            approximate = trial
            if len(trial) <= MAX_VERTICES:
                break
    if approximate is None or len(approximate) < 3:
        approximate = cv2.approxPolyDP(piece.contour, 0.10 * perimeter, True)
    vertices = contour_to_cm(approximate, paper)
    vertices = _strip_spurious_vertices(vertices)
    vertices = _merge_short_edges(vertices)
    vertices = _merge_collinear_vertices(vertices)
    vertices = _try_triangle(piece.contour, paper, vertices)
    if len(vertices) > MAX_VERTICES:
        contour = vertices.astype(np.float32).reshape(-1, 1, 2)
        simplified = cv2.approxPolyDP(
            contour,
            0.08 * cv2.arcLength(contour, True),
            True,
        )
        vertices = _strip_spurious_vertices(simplified.reshape(-1, 2))
    return vertices


def _contour_segment(
    contour: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
) -> np.ndarray:
    first_index = int(np.argmin(np.sum((contour - first) ** 2, axis=1)))
    second_index = int(np.argmin(np.sum((contour - second) ** 2, axis=1)))
    forward: list[int] = []
    index = first_index
    for _ in range(len(contour) + 2):
        forward.append(index)
        if index == second_index:
            break
        index = (index + 1) % len(contour)
    backward: list[int] = []
    index = first_index
    for _ in range(len(contour) + 2):
        backward.append(index)
        if index == second_index:
            break
        index = (index - 1) % len(contour)
    return contour[np.asarray(forward if len(forward) <= len(backward) else backward)]


def _fitted_edge_length(
    contour: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
) -> float:
    chord = float(np.linalg.norm(second - first))
    segment = _contour_segment(contour, first, second)
    if len(segment) < 3:
        return chord
    centered = segment - segment.mean(axis=0)
    if float(np.max(np.linalg.norm(centered, axis=1))) < 1e-6:
        return chord
    _, _, right = np.linalg.svd(centered, full_matrices=False)
    projections = centered @ right[0]
    span = float(projections.max() - projections.min())
    return span if span >= 0.5 * chord else chord


def analyze_pieces(
    detected: Sequence[DetectedPiece],
    paper: PaperFrame,
) -> list[AnalyzedPiece]:
    """Apply the strict physical filters used before image-mode fallback."""

    output: list[AnalyzedPiece] = []
    for index, piece in enumerate(detected):
        vertices = detect_polygon_vertices(piece, paper)
        if not 3 <= len(vertices) <= MAX_VERTICES:
            continue
        if not MIN_PIECE_AREA_CM2 <= piece.area_cm2 <= MAX_PIECE_AREA_CM2:
            continue
        contour_cm = contour_to_cm(piece.contour, paper)
        lengths = [
            _fitted_edge_length(
                contour_cm,
                vertices[edge_index],
                vertices[(edge_index + 1) % len(vertices)],
            )
            for edge_index in range(len(vertices))
        ]
        if min(lengths) < MIN_PHYSICAL_EDGE_CM * 0.46:
            continue
        output.append(AnalyzedPiece(index=index, vertices_cm=vertices))
    return output
