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
    candidates = _quadrilateral_candidates(gray)

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
    if top_width > left_height:
        width_mm, height_mm = 297.0, 210.0
    else:
        width_mm, height_mm = A4_PORTRAIT_MM
    output_width = int(round(width_mm * active.canonical_pixels_per_mm))
    output_height = int(round(height_mm * active.canonical_pixels_per_mm))
    destination = np.asarray(
        (
            (0, 0),
            (output_width - 1, 0),
            (output_width - 1, output_height - 1),
            (0, output_height - 1),
        ),
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(best, destination)
    rectified = cv2.warpPerspective(frame, matrix, (output_width, output_height))
    return RectifiedBoard(
        rectified,
        active.canonical_pixels_per_mm,
        width_mm,
        height_mm,
        matrix,
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


def _clean_polygon(points: np.ndarray, pixels_per_mm: float) -> np.ndarray:
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
        short = np.where(lengths < 8.0 * pixels_per_mm)[0]
        if len(short):
            delete_index = (int(short[np.argmin(lengths[short])]) + 1) % len(output)
            output = np.delete(output, delete_index, axis=0)
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
        trial = _clean_polygon(trial, pixels_per_mm)
        if not config.min_vertices <= len(trial) <= config.max_vertices:
            continue
        area = abs(float(cv2.contourArea(trial.astype(np.float32).reshape(-1, 1, 2))))
        error = abs(area - contour_area) / max(contour_area, 1.0)
        candidates.append((error + ratio * 0.1, trial))
    if not candidates:
        return None
    error, polygon = min(candidates, key=lambda item: item[0])
    allowed_error = config.polygon_area_error_ratio
    if len(polygon) == 4 and cv2.isContourConvex(
        polygon.astype(np.float32).reshape(-1, 1, 2)
    ):
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
    gray: np.ndarray,
    dark_gray_threshold: int,
) -> float:
    """Measure non-background ink inside a proposed physical-edge fill."""

    contour_mask = np.zeros(gray.shape, dtype=np.uint8)
    covering_mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.drawContours(contour_mask, [contour], -1, 255, thickness=cv2.FILLED)
    cv2.drawContours(
        covering_mask, [covering_contour], -1, 255, thickness=cv2.FILLED
    )
    proposed_fill = (covering_mask > 0) & (contour_mask == 0)
    fill_count = int(np.count_nonzero(proposed_fill))
    if fill_count == 0:
        return 0.0
    return float(
        np.count_nonzero(gray[proposed_fill] >= dark_gray_threshold)
    ) / fill_count


def _recover_artwork_occluded_polygon(
    contour: np.ndarray,
    gray: np.ndarray,
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
        gray,
        config.artwork_dark_gray_threshold,
    )
    if ink_support < config.artwork_hull_min_ink_support_ratio:
        return None
    return polygon


def _recover_artwork_clipped_rectangle(
    contour: np.ndarray,
    gray: np.ndarray,
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
        gray,
        config.artwork_dark_gray_threshold,
    )
    if ink_support < config.artwork_hull_min_ink_support_ratio:
        return None
    return _polygon_from_contour(box, config, pixels_per_mm)


def _artwork_aware_seed(
    image_bgr: np.ndarray,
    paper_seed: np.ndarray,
    region: np.ndarray,
    config: SolverConfig,
    pixels_per_mm: float,
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
    background_samples = active_region & ~paper
    if not np.any(background_samples):
        return cv2.bitwise_and(paper_seed, region)

    image_float = image_bgr.astype(np.float32)
    background_bgr = np.median(
        image_float[background_samples],
        axis=0,
    )
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
    gray: np.ndarray,
    config: SolverConfig,
    pixels_per_mm: float,
) -> list[DetectedFragment]:
    """Fit valid three-to-five-sided polygons to raw fragment contours."""

    fragments: list[DetectedFragment] = []
    for contour in contours:
        area_px = float(cv2.contourArea(contour))
        area_mm2 = area_px / pixels_per_mm**2
        if not config.min_piece_area_mm2 <= area_mm2 <= config.max_piece_area_mm2:
            continue
        polygon = _polygon_from_contour(contour, config, pixels_per_mm)
        recovered_polygon = _recover_artwork_occluded_polygon(
            contour,
            gray,
            config,
            pixels_per_mm,
        )
        if recovered_polygon is not None and (
            polygon is None or len(recovered_polygon) < len(polygon)
        ):
            polygon = recovered_polygon
        if polygon is not None and len(polygon) == 5:
            recovered_rectangle = _recover_artwork_clipped_rectangle(
                contour,
                gray,
                config,
                pixels_per_mm,
            )
            if recovered_rectangle is not None:
                polygon = recovered_rectangle
        if polygon is None:
            continue
        full_mask = np.zeros(gray.shape, dtype=np.uint8)
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
    artwork_seed = _artwork_aware_seed(
        image,
        paper_seed,
        region,
        active,
        board.pixels_per_mm,
    )

    stock_fragments = _fragments_from_contours(
        _extract_fragment_contours(
            paper_seed,
            paper_seed,
            board.pixels_per_mm,
        ),
        gray,
        active,
        board.pixels_per_mm,
    )
    artwork_fragments = _fragments_from_contours(
        _extract_fragment_contours(
            artwork_seed,
            paper_seed,
            board.pixels_per_mm,
        ),
        gray,
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
    if len(fragments) > active.max_piece_count:
        raise ValueError(
            f"detected {len(fragments)} fragments; maximum is {active.max_piece_count}"
        )
    if not fragments:
        raise ValueError("no valid playing-card fragments were detected")
    return fragments
