"""A4 calibration and colour-card fragment detection for Q3 images."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import cv2
import numpy as np
from shapely.geometry import Polygon as ShapelyPolygon

from .config import SolverConfig


A4_PORTRAIT_MM = (210.0, 297.0)


@dataclass(frozen=True)
class RectifiedBoard:
    image_bgr: np.ndarray
    pixels_per_mm: float
    width_mm: float
    height_mm: float
    source_to_board_px: np.ndarray
    source_corners_px: np.ndarray | None = None
    landscape_in_source: bool = False

    @property
    def corners_px(self) -> np.ndarray:
        if self.source_corners_px is not None:
            return self.source_corners_px
        return np.asarray(
            (
                (0.0, 0.0),
                (self.image_bgr.shape[1] - 1.0, 0.0),
                (self.image_bgr.shape[1] - 1.0, self.image_bgr.shape[0] - 1.0),
                (0.0, self.image_bgr.shape[0] - 1.0),
            ),
            dtype=np.float32,
        )

    @property
    def landscape_in_image(self) -> bool:
        return self.landscape_in_source


@dataclass(frozen=True)
class Divider:
    layout: Literal["top-bottom", "left-right"]
    position_mm: float
    confidence: float


@dataclass(frozen=True)
class DetectedFragment:
    contour_px: np.ndarray
    polygon_px: np.ndarray
    mask: np.ndarray
    area_mm2: float


def _order_corners(points: np.ndarray) -> np.ndarray:
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    ordered = np.empty((4, 2), dtype=np.float32)
    coordinate_sum = points.sum(axis=1)
    coordinate_difference = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(coordinate_sum)]
    ordered[2] = points[np.argmax(coordinate_sum)]
    ordered[1] = points[np.argmin(coordinate_difference)]
    ordered[3] = points[np.argmax(coordinate_difference)]
    return ordered


def _quadrilateral_candidates(gray: np.ndarray) -> list[np.ndarray]:
    height, width = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    otsu_threshold, _ = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    masks: list[np.ndarray] = [cv2.Canny(blurred, 40, 130)]
    for mode in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
        _, thresholded = cv2.threshold(blurred, otsu_threshold, 255, mode)
        masks.append(thresholded)
    output: list[np.ndarray] = []
    for mask in masks:
        mask = cv2.morphologyEx(
            mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)),
            iterations=2,
        )
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < width * height * 0.18:
                continue
            perimeter = cv2.arcLength(contour, True)
            approximate = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approximate) != 4 or not cv2.isContourConvex(approximate):
                continue
            output.append(approximate.reshape(4, 2).astype(np.float32))
    return output


def _split_board_candidate(gray: np.ndarray) -> np.ndarray | None:
    """Recover the clipped landscape board from its two dark halves."""

    height, width = gray.shape
    if height < 80 or width < 160:
        return None
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, dark = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU,
    )
    column_coverage = np.mean(dark > 0, axis=0)
    active_columns = column_coverage >= 0.20
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, active in enumerate(active_columns):
        if active and start is None:
            start = x
        elif not active and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, width - 1))

    minimum_half_width = int(round(width * 0.25))
    halves = [run for run in runs if run[1] - run[0] + 1 >= minimum_half_width]
    best_pair: tuple[int, int, int, int] | None = None
    best_score = -1.0
    for left_run in halves:
        for right_run in halves:
            left_start, left_end = left_run
            right_start, right_end = right_run
            if left_end >= right_start:
                continue
            left_width = left_end - left_start + 1
            right_width = right_end - right_start + 1
            width_ratio = left_width / max(right_width, 1)
            gap = right_start - left_end - 1
            full_width = right_end - left_start + 1
            divider_x = 0.5 * (left_end + right_start)
            if not 0.72 <= width_ratio <= 1.38:
                continue
            if not max(2.0, width * 0.002) <= gap <= width * 0.06:
                continue
            if not width * 0.65 <= full_width <= width * 0.99:
                continue
            if not width * 0.35 <= divider_x <= width * 0.65:
                continue
            divider = gray[:, left_end + 1 : right_start]
            if divider.size == 0 or float(np.mean(divider >= 155)) < 0.72:
                continue
            score = full_width * (1.0 - abs(1.0 - width_ratio))
            if score > best_score:
                best_score = score
                best_pair = (left_start, left_end, right_start, right_end)
    if best_pair is None:
        return None

    left, _, _, right = best_pair
    paper_dark = dark[:, left : right + 1] > 0
    row_coverage = np.mean(paper_dark, axis=1)
    paper_rows = np.flatnonzero(row_coverage >= 0.20)
    if paper_rows.size == 0:
        return None
    top = int(paper_rows[0])
    bottom = int(paper_rows[-1])
    paper_width = right - left
    visible_height = bottom - top
    if visible_height < height * 0.55:
        return None
    expected_height = paper_width / (297.0 / 210.0)
    if abs(paper_width / max(visible_height, 1) - 297.0 / 210.0) > 0.35:
        return None
    edge_margin = max(3, int(round(height * 0.015)))
    top_clipped = top <= edge_margin
    bottom_clipped = bottom >= height - 1 - edge_margin
    if top_clipped and not bottom_clipped:
        top = int(round(bottom - expected_height))
    elif bottom_clipped and not top_clipped:
        bottom = int(round(top + expected_height))
    elif top_clipped and bottom_clipped and expected_height > visible_height:
        overflow = expected_height - visible_height
        top = int(round(top - 0.5 * overflow))
        bottom = int(round(bottom + 0.5 * overflow))
    return np.asarray(
        ((left, top), (right, top), (right, bottom), (left, bottom)),
        dtype=np.float32,
    )


def detect_and_rectify_board(
    frame: np.ndarray,
    config: SolverConfig | None = None,
) -> RectifiedBoard:
    """Locate the A4 work area and warp it to calibrated board pixels."""

    active = config or SolverConfig()
    if frame is None or frame.ndim != 3:
        raise ValueError("a BGR colour image is required")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    split_candidate = _split_board_candidate(gray)
    candidates = _quadrilateral_candidates(gray)
    if split_candidate is not None:
        candidates.append(split_candidate)

    image_ratio = width / max(height, 1)
    target_ratios = (210.0 / 297.0, 297.0 / 210.0)
    full_frame_is_a4 = min(abs(image_ratio - ratio) for ratio in target_ratios) <= 0.035
    if full_frame_is_a4:
        inset = max(1, min(width, height) // 500)
        candidates.append(
            np.asarray(
                (
                    (inset, inset),
                    (width - 1 - inset, inset),
                    (width - 1 - inset, height - 1 - inset),
                    (inset, height - 1 - inset),
                ),
                dtype=np.float32,
            )
        )
    if not candidates:
        raise ValueError("could not find the A4 board boundary")

    best: np.ndarray | None = None
    best_score = -1.0
    for candidate in candidates:
        ordered = _order_corners(candidate)
        top = np.linalg.norm(ordered[1] - ordered[0])
        bottom = np.linalg.norm(ordered[2] - ordered[3])
        left = np.linalg.norm(ordered[3] - ordered[0])
        right = np.linalg.norm(ordered[2] - ordered[1])
        candidate_width = 0.5 * (top + bottom)
        candidate_height = 0.5 * (left + right)
        ratio = candidate_width / max(candidate_height, 1e-6)
        ratio_error = min(abs(ratio - value) for value in target_ratios)
        area = abs(float(cv2.contourArea(ordered.reshape(-1, 1, 2))))
        score = area / (1.0 + 8.0 * ratio_error)
        if ratio_error <= 0.35 and score > best_score:
            best, best_score = ordered, score
    if best is None:
        raise ValueError("detected board does not have an A4-like aspect ratio")

    top_width = float(np.linalg.norm(best[1] - best[0]))
    left_height = float(np.linalg.norm(best[3] - best[0]))
    landscape = top_width > left_height
    width_mm, height_mm = A4_PORTRAIT_MM
    output_width = int(round(width_mm * active.canonical_pixels_per_mm))
    output_height = int(round(height_mm * active.canonical_pixels_per_mm))
    source = best[[0, 3, 2, 1]] if landscape else best
    destination = np.asarray(
        (
            (0, 0),
            (output_width - 1, 0),
            (output_width - 1, output_height - 1),
            (0, output_height - 1),
        ),
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(source, destination)
    rectified = cv2.warpPerspective(frame, matrix, (output_width, output_height))
    return RectifiedBoard(
        rectified,
        active.canonical_pixels_per_mm,
        width_mm,
        height_mm,
        matrix,
        best,
        landscape,
    )


def detect_divider(
    board: RectifiedBoard,
    layout: Literal["auto", "top-bottom", "left-right"] = "auto",
) -> Divider:
    """Find the long bright separator between source and destination regions."""

    gray = cv2.cvtColor(board.image_bgr, cv2.COLOR_BGR2GRAY)
    bright = gray >= 155
    height, width = gray.shape
    row_profile = np.mean(bright[:, int(width * 0.05) : int(width * 0.95)], axis=1)
    column_profile = np.mean(bright[int(height * 0.05) : int(height * 0.95)], axis=0)

    row_start, row_end = int(height * 0.32), int(height * 0.68)
    col_start, col_end = int(width * 0.32), int(width * 0.68)
    row_index = row_start + int(np.argmax(row_profile[row_start:row_end]))
    column_index = col_start + int(np.argmax(column_profile[col_start:col_end]))
    row_score = float(row_profile[row_index])
    column_score = float(column_profile[column_index])

    if layout == "top-bottom" or (layout == "auto" and row_score >= column_score):
        if layout == "auto" and row_score < 0.35:
            row_index = height // 2
        return Divider("top-bottom", row_index / board.pixels_per_mm, row_score)
    if layout == "auto" and column_score < 0.35:
        column_index = width // 2
    return Divider("left-right", column_index / board.pixels_per_mm, column_score)


def _interior_angle(points: np.ndarray, index: int) -> float:
    current = points[index]
    first = points[index - 1] - current
    second = points[(index + 1) % len(points)] - current
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 1e-8:
        return 180.0
    cosine = float(np.clip(np.dot(first, second) / denominator, -1.0, 1.0))
    return float(np.degrees(np.arccos(cosine)))


def _line_intersection(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> np.ndarray | None:
    first_direction = first_end - first_start
    second_direction = second_end - second_start
    denominator = float(
        first_direction[0] * second_direction[1]
        - first_direction[1] * second_direction[0]
    )
    if abs(denominator) <= 1e-6:
        return None
    offset = second_start - first_start
    scale = float(
        offset[0] * second_direction[1]
        - offset[1] * second_direction[0]
    ) / denominator
    return first_start + scale * first_direction


def _replace_short_edge_with_corner(
    points: np.ndarray,
    edge_index: int,
    pixels_per_mm: float,
) -> np.ndarray | None:
    rotated = np.roll(points, -edge_index, axis=0)
    first, second = rotated[0], rotated[1]
    intersection = _line_intersection(rotated[-1], first, second, rotated[2])
    if intersection is None:
        return None
    short_length = float(np.linalg.norm(second - first))
    maximum_shift = max(8.0 * pixels_per_mm, 2.0 * short_length)
    if float(np.linalg.norm(intersection - 0.5 * (first + second))) > maximum_shift:
        return None
    return np.vstack((intersection, rotated[2:])).astype(np.float32)


def _clean_polygon(
    points: np.ndarray,
    config: SolverConfig,
    pixels_per_mm: float,
) -> np.ndarray:
    output = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    for _ in range(8):
        if len(output) <= 3:
            break
        lengths = np.asarray(
            [
                np.linalg.norm(output[(index + 1) % len(output)] - output[index])
                for index in range(len(output))
            ]
        )
        angles = np.asarray([_interior_angle(output, index) for index in range(len(output))])
        collinear = np.where(angles >= 166.0)[0]
        if len(collinear):
            output = np.delete(output, int(collinear[0]), axis=0)
            continue
        minimum_real_edge = max(
            8.0,
            config.min_physical_edge_mm - config.length_tolerance_mm,
        ) * pixels_per_mm
        short = np.where(lengths < minimum_real_edge)[0]
        if len(short):
            edge_index = int(short[np.argmin(lengths[short])])
            merged = _replace_short_edge_with_corner(
                output,
                edge_index,
                pixels_per_mm,
            )
            if merged is not None:
                output = merged
                continue
        break
    return output


def _polygon_from_contour(
    contour: np.ndarray,
    config: SolverConfig,
    pixels_per_mm: float,
) -> np.ndarray | None:
    perimeter = cv2.arcLength(contour, True)
    contour_area = float(cv2.contourArea(contour))
    candidates: list[tuple[float, np.ndarray]] = []
    for ratio in (0.006, 0.009, 0.012, 0.016, 0.022, 0.03, 0.04, 0.055, 0.075):
        trial = cv2.approxPolyDP(contour, ratio * perimeter, True).reshape(-1, 2)
        trial = _clean_polygon(trial, config, pixels_per_mm)
        if not config.min_vertices <= len(trial) <= config.max_vertices:
            continue
        area = abs(float(cv2.contourArea(trial.astype(np.float32).reshape(-1, 1, 2))))
        error = abs(area - contour_area) / max(contour_area, 1.0)
        candidates.append((error + ratio * 0.1, trial))
    if not candidates:
        return None
    error, polygon = min(candidates, key=lambda item: item[0])
    allowed_error = config.polygon_area_error_ratio
    polygon_cv = polygon.astype(np.float32).reshape(-1, 1, 2)
    if len(polygon) == 3:
        # Red/black artwork often shortens the white-stock seed on triangular
        # cuts, so the fitted triangle area error is naturally larger than for
        # mostly white quadrilateral fragments.
        allowed_error = config.quadrilateral_area_error_ratio
    elif len(polygon) == 4 and cv2.isContourConvex(polygon_cv):
        # Dark face-card artwork can carve deep holes out of the white-stock
        # seed.  A stable convex quadrilateral still recovers the physical
        # paper boundary, but its area error is naturally larger than for a
        # mostly white fragment.  Keep this fallback specific to four-sided
        # pieces so arbitrary textured blobs are not accepted as polygons.
        allowed_error = config.quadrilateral_area_error_ratio
    if error > allowed_error:
        return None
    return polygon.astype(np.float32)


def _proposed_fill_ink_support(
    contour: np.ndarray,
    covering_contour: np.ndarray,
    image_bgr: np.ndarray,
    background_bgr: np.ndarray,
    background_distance_threshold: float,
) -> float:
    """Measure non-background ink inside a proposed physical-edge fill."""

    contour_mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    covering_mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, 255, thickness=cv2.FILLED)
    cv2.drawContours(
        covering_mask, [covering_contour], -1, 255, thickness=cv2.FILLED
    )
    proposed_fill = (covering_mask > 0) & (contour_mask == 0)
    fill_count = int(np.count_nonzero(proposed_fill))
    if fill_count == 0:
        return 0.0
    pixels = image_bgr[proposed_fill].astype(np.float32)
    distances = np.linalg.norm(pixels - background_bgr, axis=1)
    return float(np.count_nonzero(distances >= background_distance_threshold)) / fill_count


def _recover_artwork_occluded_polygon(
    contour: np.ndarray,
    image_bgr: np.ndarray,
    background_bgr: np.ndarray,
    background_distance_threshold: float,
    config: SolverConfig,
    pixels_per_mm: float,
) -> np.ndarray | None:
    """Restore a convex paper edge hidden by dark ink touching a cut edge.

    A black pip connected to the black board makes the white-stock contour
    look concave.  A real concave cut has the same silhouette, so convex-hull
    recovery is allowed only when most pixels in the proposed fill are
    visibly brighter than the board background.  This is evidence that the
    missing support is printed card material rather than empty board.
    """

    hull = cv2.convexHull(contour)
    contour_area = float(cv2.contourArea(contour))
    hull_area = float(cv2.contourArea(hull))
    if hull_area <= 1e-9 or contour_area <= 1e-9:
        return None
    added_area_ratio = (hull_area - contour_area) / hull_area
    if not 0.0 < added_area_ratio <= config.artwork_hull_max_added_area_ratio:
        return None

    polygon = _polygon_from_contour(hull, config, pixels_per_mm)
    if polygon is None:
        return None

    ink_support = _proposed_fill_ink_support(
        contour,
        hull,
        image_bgr,
        background_bgr,
        background_distance_threshold,
    )
    if ink_support < config.artwork_hull_min_ink_support_ratio:
        return None
    return polygon


def _recover_artwork_clipped_rectangle(
    contour: np.ndarray,
    image_bgr: np.ndarray,
    background_bgr: np.ndarray,
    background_distance_threshold: float,
    config: SolverConfig,
    pixels_per_mm: float,
) -> np.ndarray | None:
    """Restore a rectangular corner chamfered by dark artwork."""

    box = cv2.boxPoints(cv2.minAreaRect(contour)).astype(np.float32).reshape(-1, 1, 2)
    contour_area = float(cv2.contourArea(contour))
    box_area = float(cv2.contourArea(box))
    if box_area <= 1e-9 or contour_area <= 1e-9:
        return None
    added_area_ratio = (box_area - contour_area) / box_area
    if not 0.0 < added_area_ratio <= config.artwork_hull_max_added_area_ratio:
        return None
    ink_support = _proposed_fill_ink_support(
        contour,
        box.astype(np.int32),
        image_bgr,
        background_bgr,
        background_distance_threshold,
    )
    if ink_support < config.artwork_hull_min_ink_support_ratio:
        return None
    return _polygon_from_contour(box, config, pixels_per_mm)


def _background_colour_model(
    image_bgr: np.ndarray,
    paper_seed: np.ndarray,
    region: np.ndarray,
    config: SolverConfig,
) -> tuple[np.ndarray, float]:
    active_region = region > 0
    paper = paper_seed > 0
    background_samples = active_region & ~paper
    if not np.any(background_samples):
        return np.zeros(3, dtype=np.float32), config.artwork_background_min_color_distance
    image_float = image_bgr.astype(np.float32)
    background_bgr = np.median(image_float[background_samples], axis=0)
    color_distance = np.linalg.norm(image_float - background_bgr, axis=2)
    background_noise = float(
        np.percentile(
            color_distance[background_samples],
            config.artwork_background_noise_percentile,
        )
    )
    distance_threshold = max(
        config.artwork_background_min_color_distance,
        config.artwork_background_noise_multiplier * background_noise,
    )
    return background_bgr, distance_threshold


def _artwork_aware_seed(
    image_bgr: np.ndarray,
    paper_seed: np.ndarray,
    region: np.ndarray,
    config: SolverConfig,
    pixels_per_mm: float,
    background_bgr: np.ndarray,
    distance_threshold: float,
) -> np.ndarray:
    """Add printed artwork that differs from the surrounding dark board.

    White-stock segmentation alone cuts a notch into a fragment whenever a
    black pip reaches a cut edge.  The board normally occupies most of the
    source region, so its median BGR colour is a robust background estimate.
    A noise-adaptive colour-distance threshold separates black printing from
    that background.  Entire non-background connected components are retained
    when any part lies next to the known paper seed.  Keeping the full
    component matters for a large pip: clipping it to a narrow dilation band
    would leave a smaller but still significant notch.  Unrelated board
    texture is excluded because it does not touch paper.

    If ink and board have exactly the same observed colour, no pixel-only
    method can separate them; the existing geometric hull recovery remains
    the fallback for that case.
    """

    paper = paper_seed > 0
    active_region = region > 0
    image_float = image_bgr.astype(np.float32)
    color_distance = np.linalg.norm(image_float - background_bgr, axis=2)

    radius = max(1, int(round(config.artwork_support_distance_mm * pixels_per_mm)))
    kernel_size = 2 * radius + 1
    near_paper = cv2.dilate(
        paper_seed,
        cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (kernel_size, kernel_size),
        ),
        iterations=1,
    ) > 0
    artwork_candidates = (
        active_region
        & ~paper
        & (color_distance >= distance_threshold)
    )
    component_count, component_labels = cv2.connectedComponents(
        artwork_candidates.astype(np.uint8),
        connectivity=8,
    )
    if component_count <= 1:
        printed_artwork = np.zeros_like(paper)
    else:
        touching_labels = np.unique(
            component_labels[artwork_candidates & near_paper]
        )
        touching_labels = touching_labels[touching_labels > 0]
        printed_artwork = np.isin(component_labels, touching_labels)
    return np.where(
        active_region & (paper | printed_artwork),
        255,
        0,
    ).astype(np.uint8)


def _extract_fragment_contours(
    seed: np.ndarray,
    paper_seed: np.ndarray,
    pixels_per_mm: float,
) -> list[np.ndarray]:
    """Return grouped contours that contain high-confidence card stock."""

    # Rank strokes can cut the white seed into two components even though the
    # paper itself is continuous. Close gaps up to roughly 2 mm; official
    # fragments have much larger spacing and therefore remain separate.
    close_size = max(3, int(round(2.0 * pixels_per_mm)) | 1)
    prepared = cv2.morphologyEx(
        seed,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (close_size, close_size)),
        iterations=1,
    )
    prepared = cv2.morphologyEx(
        prepared,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )
    raw_contours, _ = cv2.findContours(
        prepared,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    minimum_component_area = max(20.0, 5.0 * pixels_per_mm**2)
    retained_contours: list[np.ndarray] = []
    for contour in raw_contours:
        if cv2.contourArea(contour) < minimum_component_area:
            continue
        contour_mask = np.zeros(seed.shape, dtype=np.uint8)
        cv2.drawContours(
            contour_mask,
            [contour],
            -1,
            255,
            thickness=cv2.FILLED,
        )
        # Every physical fragment must contain a meaningful amount of the
        # high-confidence white/red paper seed. This rejects isolated board
        # texture admitted by the background-distance mask.
        stock_overlap = int(
            np.count_nonzero((contour_mask > 0) & (paper_seed > 0))
        )
        if stock_overlap >= minimum_component_area:
            retained_contours.append(contour)

    # A black rank or line can divide one paper region into disconnected
    # colour components. Group components within 3 mm, then reconstruct their
    # common outer support. Official fragments are placed farther apart.
    parents = list(range(len(retained_contours)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(first: int, second: int) -> None:
        first_root, second_root = find(first), find(second)
        if first_root != second_root:
            parents[second_root] = first_root

    grouping_gap = int(round(3.0 * pixels_per_mm))
    boxes = [cv2.boundingRect(contour) for contour in retained_contours]
    component_polygons = [
        ShapelyPolygon(contour.reshape(-1, 2)).buffer(0)
        for contour in retained_contours
    ]
    for first in range(len(retained_contours)):
        x1, y1, w1, h1 = boxes[first]
        for second in range(first + 1, len(retained_contours)):
            x2, y2, w2, h2 = boxes[second]
            horizontal_gap = max(0, x1 - (x2 + w2), x2 - (x1 + w1))
            vertical_gap = max(0, y1 - (y2 + h2), y2 - (y1 + h1))
            if (
                horizontal_gap <= grouping_gap
                and vertical_gap <= grouping_gap
                and component_polygons[first].distance(component_polygons[second])
                <= grouping_gap
            ):
                union(first, second)

    groups: dict[int, list[np.ndarray]] = {}
    for index, contour in enumerate(retained_contours):
        groups.setdefault(find(index), []).append(contour)
    contours: list[np.ndarray] = []
    for group in groups.values():
        contours.append(
            group[0]
            if len(group) == 1
            else cv2.convexHull(np.concatenate(group, axis=0))
        )
    return contours


def _fragments_from_contours(
    contours: list[np.ndarray],
    image_bgr: np.ndarray,
    background_bgr: np.ndarray,
    background_distance_threshold: float,
    config: SolverConfig,
    pixels_per_mm: float,
) -> list[DetectedFragment]:
    """Fit valid three-to-five-sided polygons to raw fragment contours."""

    fragments: list[DetectedFragment] = []
    image_height, image_width = image_bgr.shape[:2]
    boundary_margin = max(2, int(round(1.5 * pixels_per_mm)))
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if (
            x <= boundary_margin
            or y <= boundary_margin
            or x + width >= image_width - boundary_margin
            or y + height >= image_height - boundary_margin
        ):
            continue
        area_px = float(cv2.contourArea(contour))
        area_mm2 = area_px / pixels_per_mm**2
        if not config.min_piece_area_mm2 <= area_mm2 <= config.max_piece_area_mm2:
            continue
        polygon = _polygon_from_contour(contour, config, pixels_per_mm)
        recovered_polygon = _recover_artwork_occluded_polygon(
            contour,
            image_bgr,
            background_bgr,
            background_distance_threshold,
            config,
            pixels_per_mm,
        )
        if recovered_polygon is not None:
            polygon = recovered_polygon
        if polygon is not None and len(polygon) == 5:
            recovered_rectangle = _recover_artwork_clipped_rectangle(
                contour,
                image_bgr,
                background_bgr,
                background_distance_threshold,
                config,
                pixels_per_mm,
            )
            if recovered_rectangle is not None:
                polygon = recovered_rectangle
        if polygon is None:
            continue
        full_mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
        # The fitted polygon is physical paper support. Filling the raw white
        # contour would retain notches made by dark artwork and would remove
        # exactly the texture later needed for seam checks.
        cv2.drawContours(
            full_mask,
            [polygon.astype(np.int32).reshape(-1, 1, 2)],
            -1,
            255,
            thickness=cv2.FILLED,
        )
        fragments.append(DetectedFragment(contour, polygon, full_mask, area_mm2))
    return fragments


def _minimum_fragment_edge_mm(
    fragments: list[DetectedFragment],
    pixels_per_mm: float,
) -> float:
    """Return the shortest fitted edge, or infinity for an empty set."""

    return min(
        (
            float(
                np.linalg.norm(
                    fragment.polygon_px[(index + 1) % len(fragment.polygon_px)]
                    - fragment.polygon_px[index]
                )
            )
            / pixels_per_mm
            for fragment in fragments
            for index in range(len(fragment.polygon_px))
        ),
        default=math.inf,
    )


def detect_fragments(
    board: RectifiedBoard,
    divider: Divider,
    config: SolverConfig | None = None,
) -> list[DetectedFragment]:
    """Segment white card stock while retaining dark printing as texture."""

    active = config or SolverConfig()
    image = board.image_bgr
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    white_stock = (gray >= 105) & (hsv[:, :, 1] <= 125)
    red_print = (
        (((hsv[:, :, 0] <= 15) | (hsv[:, :, 0] >= 165)))
        & (hsv[:, :, 1] >= 70)
        & (hsv[:, :, 2] >= 55)
    )
    paper_seed = np.where(white_stock | red_print, 255, 0).astype(np.uint8)

    region = np.zeros(paper_seed.shape, dtype=np.uint8)
    exclusion = int(round(active.divider_exclusion_mm * board.pixels_per_mm))
    divider_px = int(round(divider.position_mm * board.pixels_per_mm))
    if divider.layout == "top-bottom":
        region[: max(0, divider_px - exclusion), :] = 255
    else:
        region[:, : max(0, divider_px - exclusion)] = 255
    paper_seed = cv2.bitwise_and(paper_seed, region)
    background_bgr, background_distance_threshold = _background_colour_model(
        image,
        paper_seed,
        region,
        active,
    )
    artwork_seed = _artwork_aware_seed(
        image,
        paper_seed,
        region,
        active,
        board.pixels_per_mm,
        background_bgr,
        background_distance_threshold,
    )

    stock_fragments = _fragments_from_contours(
        _extract_fragment_contours(
            paper_seed,
            paper_seed,
            board.pixels_per_mm,
        ),
        image,
        background_bgr,
        background_distance_threshold,
        active,
        board.pixels_per_mm,
    )
    artwork_fragments = _fragments_from_contours(
        _extract_fragment_contours(
            artwork_seed,
            paper_seed,
            board.pixels_per_mm,
        ),
        image,
        background_bgr,
        background_distance_threshold,
        active,
        board.pixels_per_mm,
    )

    fragments = stock_fragments
    if not fragments:
        fragments = artwork_fragments
    elif len(artwork_fragments) == len(stock_fragments):
        stock_minimum = _minimum_fragment_edge_mm(
            stock_fragments,
            board.pixels_per_mm,
        )
        artwork_minimum = _minimum_fragment_edge_mm(
            artwork_fragments,
            board.pixels_per_mm,
        )
        repair_threshold = (
            active.min_physical_edge_mm - active.length_tolerance_mm
        )
        # Preserve the proven white-stock path unless it contains an edge that
        # is implausibly short under the official geometry and the alternative
        # both removes that defect and improves it by a full length tolerance.
        if (
            stock_minimum < repair_threshold <= artwork_minimum
            and artwork_minimum - stock_minimum >= active.length_tolerance_mm
        ):
            fragments = artwork_fragments

    def centre(fragment: DetectedFragment) -> tuple[float, float]:
        moments = cv2.moments(fragment.contour_px)
        return (
            moments["m10"] / max(moments["m00"], 1e-9),
            moments["m01"] / max(moments["m00"], 1e-9),
        )

    fragments.sort(key=lambda fragment: (centre(fragment)[1], centre(fragment)[0]))
    if not fragments:
        raise ValueError("no valid playing-card fragments were detected")
    return fragments
