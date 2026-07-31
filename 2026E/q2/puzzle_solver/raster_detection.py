"""Standalone raster-to-polygon detection for Q2-style board images.

The geometric solver does not need this module.  It is used only by the
optional local-image adapter and intentionally contains no template matching,
camera control, or robot-specific code.  Coordinates in this module use
centimetres to match the A4 calibration; ``image_input`` converts the final
vertices to the solver's millimetre unit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

import cv2
import numpy as np


A4_WIDTH_CM = 21.0
A4_HEIGHT_CM = 29.7
DEFAULT_HSV_RANGES = (((0, 0, 120), (180, 100, 255)),)
WHITE_DIVIDER_GRAY_THRESHOLD = 160
BLACK_PAPER_GRAY_THRESHOLD = 90
A4_CANVAS_RATIO_TOLERANCE = 0.02
A4_CANVAS_DARK_BORDER_RATIO = 0.90
PAPER_FRAME_MARGIN_PX = 20
MAX_PIECES = 4
MAX_VERTICES = 5
MIN_DETECTED_AREA_CM2 = 2.0
MAX_DETECTED_AREA_CM2 = 55.0
AREA_MEASUREMENT_TOLERANCE_CM2 = 0.1
MERGE_SHORT_EDGE_CM = 1.0
MAX_SIMPLIFICATION_AREA_LOSS_RATIO = 0.08
PROTECTED_SHORT_EDGE_CM = 0.4
ADAPTIVE_APPROXIMATION_RATIOS = (
    0.005,
    0.0075,
    0.010,
    0.0125,
    0.015,
    0.0175,
    0.020,
    0.0225,
)


@dataclass(frozen=True)
class PaperFrame:
    """Detected A4 paper quadrilateral and approximate image scale."""

    corners_px: np.ndarray
    px_per_cm: float
    width_cm: float
    height_cm: float


@dataclass(frozen=True)
class BoardDivider:
    """Detected board split direction and coordinate in centimetres."""

    layout: Literal["top-bottom", "left-right"]
    position_cm: float


@dataclass(frozen=True)
class DetectedPiece:
    """One segmented raster contour in calibrated board coordinates."""

    contour: np.ndarray
    center_cm: tuple[float, float]
    area_cm2: float
    in_source_region: bool


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
    portrait_error = abs(observed_ratio - A4_WIDTH_CM / A4_HEIGHT_CM)
    landscape_error = abs(observed_ratio - A4_HEIGHT_CM / A4_WIDTH_CM)
    if min(portrait_error, landscape_error) > 0.12:
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
    image_ratio = width / max(height, 1)
    a4_ratio_error = min(
        abs(image_ratio - A4_WIDTH_CM / A4_HEIGHT_CM),
        abs(image_ratio - A4_HEIGHT_CM / A4_WIDTH_CM),
    )
    border_pixels = np.concatenate(
        (gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1])
    )
    dark_border_ratio = float(
        np.mean(border_pixels < BLACK_PAPER_GRAY_THRESHOLD)
    )
    if (
        a4_ratio_error <= A4_CANVAS_RATIO_TOLERANCE
        and dark_border_ratio >= A4_CANVAS_DARK_BORDER_RATIO
    ):
        margin = min(PAPER_FRAME_MARGIN_PX, width // 10, height // 10)
        return _make_paper_frame(
            np.asarray(
                (
                    (margin, margin),
                    (width - margin, margin),
                    (width - margin, height - margin),
                    (margin, height - margin),
                ),
                dtype=np.float32,
            )
        )

    content_frame = _find_paper_frame_from_content(gray)
    if content_frame is not None:
        ordered = _order_corners(content_frame)
        return _make_paper_frame(ordered)

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
        margin = PAPER_FRAME_MARGIN_PX
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
    return _make_paper_frame(ordered)


def _make_paper_frame(ordered_corners: np.ndarray) -> PaperFrame:
    """Assign physical A4 dimensions from the detected image orientation."""

    width_px = float(np.linalg.norm(ordered_corners[1] - ordered_corners[0]))
    height_px = float(np.linalg.norm(ordered_corners[3] - ordered_corners[0]))
    if width_px > height_px:
        width_cm, height_cm = A4_HEIGHT_CM, A4_WIDTH_CM
    else:
        width_cm, height_cm = A4_WIDTH_CM, A4_HEIGHT_CM
    return PaperFrame(
        corners_px=ordered_corners,
        px_per_cm=height_px / height_cm,
        width_cm=width_cm,
        height_cm=height_cm,
    )


def _perspective_matrix(paper: PaperFrame) -> np.ndarray:
    destination = np.asarray(
        (
            (0, 0),
            (paper.width_cm, 0),
            (paper.width_cm, paper.height_cm),
            (0, paper.height_cm),
        ),
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


def _horizontal_divider_candidate(
    frame: np.ndarray,
    paper: PaperFrame,
) -> tuple[float, float] | None:
    """Return horizontal coordinate and normalized line length."""

    top_left, top_right, _, bottom_left = paper.corners_px
    middle_y = int(top_left[1] + (bottom_left[1] - top_left[1]) * 0.5)
    left_x = int(top_left[0])
    right_x = int(top_right[0])
    y_start = max(0, middle_y - 40)
    region = frame[y_start : middle_y + 40, left_x:right_x]
    if region.size == 0:
        return None
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
        return None
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
        return None
    position_cm = _point_to_cm(np.asarray((left_x, best_y)), paper)[1]
    paper_width_px = max(1.0, float(np.linalg.norm(top_right - top_left)))
    return (position_cm, best_length / paper_width_px)


def _vertical_divider_candidate(
    frame: np.ndarray,
    paper: PaperFrame,
) -> tuple[float, float] | None:
    """Return vertical coordinate and normalized line length."""

    top_left, top_right, bottom_right, _ = paper.corners_px
    middle_x = int(top_left[0] + (top_right[0] - top_left[0]) * 0.5)
    top_y = int(min(top_left[1], top_right[1]))
    bottom_y = int(max(bottom_right[1], paper.corners_px[3, 1]))
    x_start = max(0, middle_x - 40)
    region = frame[top_y:bottom_y, x_start : middle_x + 40]
    if region.size == 0:
        return None
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
        return None
    best_x: float | None = None
    best_length = 0
    for first_x, first_y, second_x, second_y in lines.reshape(-1, 4):
        if abs(second_x - first_x) > 10:
            continue
        length = abs(second_y - first_y)
        if length > best_length:
            best_length = length
            best_x = (first_x + second_x) / 2.0 + x_start
    if best_x is None:
        return None
    position_cm = _point_to_cm(np.asarray((best_x, top_y)), paper)[0]
    paper_height_px = max(1.0, float(np.linalg.norm(bottom_right - top_right)))
    return (position_cm, best_length / paper_height_px)


def detect_board_divider(frame: np.ndarray, paper: PaperFrame) -> BoardDivider:
    """Detect whether the work board is split horizontally or vertically."""

    horizontal = _horizontal_divider_candidate(frame, paper)
    vertical = _vertical_divider_candidate(frame, paper)
    if horizontal is None and vertical is None:
        return BoardDivider("top-bottom", paper.height_cm / 2.0)
    if vertical is not None and (
        horizontal is None or vertical[1] > horizontal[1]
    ):
        return BoardDivider("left-right", vertical[0])
    assert horizontal is not None
    return BoardDivider("top-bottom", horizontal[0])


def detect_divider_line(frame: np.ndarray, paper: PaperFrame) -> float:
    """Backward-compatible horizontal divider coordinate."""

    candidate = _horizontal_divider_candidate(frame, paper)
    return candidate[0] if candidate is not None else paper.height_cm / 2.0


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
    divider_position_cm: float,
    hsv_ranges: Sequence[
        tuple[tuple[int, int, int], tuple[int, int, int]]
    ] = DEFAULT_HSV_RANGES,
    layout: Literal["top-bottom", "left-right"] = "top-bottom",
) -> list[DetectedPiece]:
    """Segment white fragments from the board's source region."""

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
        if not (
            MIN_DETECTED_AREA_CM2 - AREA_MEASUREMENT_TOLERANCE_CM2
            <= area_cm2
            <= MAX_DETECTED_AREA_CM2 + AREA_MEASUREMENT_TOLERANCE_CM2
        ):
            continue
        (center_x, center_y), _, _ = cv2.minAreaRect(contour)
        center_cm = _point_to_cm(np.asarray((center_x, center_y)), paper)
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
                area_cm2=float(area_cm2),
                in_source_region=(
                    center_cm[1] < divider_position_cm
                    if layout == "top-bottom"
                    else center_cm[0] < divider_position_cm
                ),
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


def _clean_polygon_vertices(vertices: np.ndarray) -> np.ndarray:
    """Apply the established noise cleanup to one polygon candidate."""

    cleaned = _strip_spurious_vertices(vertices)
    cleaned = _merge_short_edges(cleaned)
    return _merge_collinear_vertices(cleaned)


def _polygon_area_loss_ratio(
    contour_cm: np.ndarray,
    vertices_cm: np.ndarray,
) -> float:
    """Measure how much contour area a simplified polygon fails to retain."""

    contour_area = abs(
        float(cv2.contourArea(contour_cm.astype(np.float32).reshape(-1, 1, 2)))
    )
    if contour_area <= 1e-9 or len(vertices_cm) < 3:
        return float("inf")
    polygon_area = abs(
        float(cv2.contourArea(vertices_cm.astype(np.float32).reshape(-1, 1, 2)))
    )
    return abs(contour_area - polygon_area) / contour_area


def _polygon_boundary_error_cm(
    contour_cm: np.ndarray,
    vertices_cm: np.ndarray,
) -> float:
    """Return the 95th-percentile contour-to-polygon boundary distance."""

    polygon = vertices_cm.astype(np.float32).reshape(-1, 1, 2)
    distances = [
        abs(cv2.pointPolygonTest(polygon, (float(point[0]), float(point[1])), True))
        for point in contour_cm.reshape(-1, 2)
    ]
    return float(np.percentile(distances, 95)) if distances else float("inf")


def _adaptive_polygon_candidate(
    piece: DetectedPiece,
    paper: PaperFrame,
    current: np.ndarray,
) -> np.ndarray:
    """Recover a finer 3--5 vertex fit when the fast fit loses real area.

    Most images retain the original fast path exactly.  Only a candidate that
    loses more than eight percent of the calibrated raster contour reaches
    this fallback.  Candidate choice first favours the simplest valid polygon,
    then area fidelity and boundary distance.
    """

    contour_cm = contour_to_cm(piece.contour, paper)
    current_loss = _polygon_area_loss_ratio(contour_cm, current)
    if current_loss <= MAX_SIMPLIFICATION_AREA_LOSS_RATIO:
        return current

    perimeter = cv2.arcLength(piece.contour, True)
    candidates: list[tuple[int, float, float, float, np.ndarray]] = []
    for ratio in ADAPTIVE_APPROXIMATION_RATIOS:
        approximate = cv2.approxPolyDP(piece.contour, ratio * perimeter, True)
        vertices = _clean_polygon_vertices(contour_to_cm(approximate, paper))
        if not 3 <= len(vertices) <= MAX_VERTICES:
            continue
        lengths = [
            float(np.linalg.norm(vertices[(index + 1) % len(vertices)] - vertices[index]))
            for index in range(len(vertices))
        ]
        if min(lengths) < PROTECTED_SHORT_EDGE_CM:
            continue
        area_loss = _polygon_area_loss_ratio(contour_cm, vertices)
        if area_loss > MAX_SIMPLIFICATION_AREA_LOSS_RATIO:
            continue
        boundary_error = _polygon_boundary_error_cm(contour_cm, vertices)
        candidates.append((len(vertices), area_loss, boundary_error, -ratio, vertices))

    if not candidates:
        return current
    return min(candidates, key=lambda item: item[:4])[4]


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
    vertices = _clean_polygon_vertices(contour_to_cm(approximate, paper))
    # A genuine triangle is already reduced to three vertices by the first
    # Douglas-Peucker pass.  Retrying with a very large epsilon based only on
    # area can turn a concave pentagon into a triangle even though its missing
    # corners are real (q2_9 is such a case), destroying its matching edges.
    if len(vertices) > MAX_VERTICES:
        contour = vertices.astype(np.float32).reshape(-1, 1, 2)
        simplified = cv2.approxPolyDP(
            contour,
            0.08 * cv2.arcLength(contour, True),
            True,
        )
        vertices = _strip_spurious_vertices(simplified.reshape(-1, 2))
    return _adaptive_polygon_candidate(piece, paper, vertices)

