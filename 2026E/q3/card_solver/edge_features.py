"""Extract canonical colour and line profiles along every polygon edge."""

from __future__ import annotations

import math

import cv2
import numpy as np

from .config import PatternConfig
from .geometry import Point, signed_area
from .models import CornerMarker, EdgeFeature, PieceObservation


def _extract_foreground_mask(
    observation: PieceObservation,
    config: PatternConfig,
) -> tuple[np.ndarray, float, float]:
    """Return red/black card ink while removing the fitted piece boundary."""

    lab = cv2.cvtColor(observation.texture_bgr, cv2.COLOR_BGR2LAB)
    lightness = lab[:, :, 0].astype(np.float32) * (100.0 / 255.0)
    black = lightness < config.black_lightness_threshold
    red = (
        (lab[:, :, 1].astype(np.float32) >= config.red_a_threshold)
        & (lightness >= config.black_lightness_threshold)
    )
    exclusion_px = max(
        1, int(round(config.corner_boundary_exclusion_mm * observation.pixels_per_mm))
    )
    kernel_size = exclusion_px * 2 + 1
    interior = cv2.erode(
        (observation.mask > 0).astype(np.uint8),
        np.ones((kernel_size, kernel_size), dtype=np.uint8),
    )
    red &= interior > 0
    black &= interior > 0
    pixel_area_mm2 = 1.0 / (observation.pixels_per_mm**2)
    foreground = (red | black).astype(np.uint8)
    return (
        foreground,
        float(np.count_nonzero(red)) * pixel_area_mm2,
        float(np.count_nonzero(black)) * pixel_area_mm2,
    )


def _extract_corner_markers(
    observation: PieceObservation,
    config: PatternConfig,
    foreground: np.ndarray,
) -> tuple[tuple[float, ...], tuple[CornerMarker, ...], np.ndarray]:
    """Score vertices containing a rank plus small suit card index.

    Red or black connected components are measured in physical units.  A
    single clipped centre pip at a cut vertex is deliberately insufficient:
    a card corner marker requires at least two medium/small components.
    """

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        foreground, connectivity=8
    )
    pixel_area_mm2 = 1.0 / (observation.pixels_per_mm**2)
    eligible: list[int] = []
    component_centres: dict[int, Point] = {}
    component_areas: dict[int, float] = {}
    for label in range(1, component_count):
        area_mm2 = float(stats[label, cv2.CC_STAT_AREA]) * pixel_area_mm2
        if (
            config.corner_min_component_area_mm2
            <= area_mm2
            <= config.corner_max_component_area_mm2
        ):
            eligible.append(label)
            centre_x = (
                float(stats[label, cv2.CC_STAT_LEFT])
                + float(stats[label, cv2.CC_STAT_WIDTH]) * 0.5
            )
            centre_y = (
                float(stats[label, cv2.CC_STAT_TOP])
                + float(stats[label, cv2.CC_STAT_HEIGHT]) * 0.5
            )
            component_centres[label] = Point(
                (centre_x + observation.crop_origin_px[0])
                / observation.pixels_per_mm,
                (centre_y + observation.crop_origin_px[1])
                / observation.pixels_per_mm,
            )
            component_areas[label] = area_mm2

    # Connected groups model the rank and its small suit as one semantic card
    # index.  This avoids counting that same index once for each nearby polygon
    # vertex when a fitted cut edge is short.
    neighbours = {label: set() for label in eligible}
    for index, first in enumerate(eligible):
        for second in eligible[index + 1 :]:
            if (
                math.dist(
                    component_centres[first].as_tuple(),
                    component_centres[second].as_tuple(),
                )
                <= config.corner_group_distance_mm
            ):
                neighbours[first].add(second)
                neighbours[second].add(first)
    groups: list[list[int]] = []
    unseen = set(eligible)
    while unseen:
        seed = unseen.pop()
        group = [seed]
        pending = [seed]
        while pending:
            current = pending.pop()
            attached = neighbours[current] & unseen
            unseen.difference_update(attached)
            group.extend(attached)
            pending.extend(attached)
        if config.corner_min_components <= len(group) <= config.corner_max_components:
            groups.append(group)

    markers: list[CornerMarker] = []
    marker_labels: set[int] = set()
    vertex_scores = [0.0] * len(observation.piece.vertices)
    for group in groups:
        total_area = sum(component_areas[label] for label in group)
        centre = Point(
            sum(
                component_centres[label].x * component_areas[label]
                for label in group
            )
            / total_area,
            sum(
                component_centres[label].y * component_areas[label]
                for label in group
            )
            / total_area,
        )
        distances = [
            math.dist(centre.as_tuple(), vertex.as_tuple())
            for vertex in observation.piece.vertices
        ]
        nearest_vertex = int(np.argmin(distances))
        nearest_distance = distances[nearest_vertex]
        if nearest_distance > config.corner_search_radius_mm:
            continue
        proximity = 1.0 - nearest_distance / max(config.corner_search_radius_mm, 1e-9)
        score = (
            float(len(group))
            + min(1.0, total_area / 20.0)
            + 0.5 * proximity
        )
        # In every standard corner index the rank/letter is nearest the card
        # corner and the small suit is farther inward.  This direction is
        # colour- and suit-independent, and later distinguishes the canonical
        # top-left/bottom-right layout from its horizontal mirror.
        ordered_labels = sorted(
            group,
            key=lambda label: math.dist(
                component_centres[label].as_tuple(),
                observation.piece.vertices[nearest_vertex].as_tuple(),
            ),
        )
        outer = component_centres[ordered_labels[0]]
        inner = component_centres[ordered_labels[-1]]
        direction_length = math.dist(outer.as_tuple(), inner.as_tuple())
        inward_direction = (
            Point(
                (inner.x - outer.x) / direction_length,
                (inner.y - outer.y) / direction_length,
            )
            if direction_length >= config.corner_direction_min_separation_mm
            else None
        )
        markers.append(
            CornerMarker(centre, score, len(group), inward_direction)
        )
        marker_labels.update(group)
        vertex_scores[nearest_vertex] = max(vertex_scores[nearest_vertex], score)
    markers.sort(key=lambda marker: -marker.score)
    symmetry_foreground = foreground.copy()
    if marker_labels:
        symmetry_foreground[np.isin(labels, tuple(marker_labels))] = 0
    return tuple(vertex_scores), tuple(markers), symmetry_foreground


def _smooth_profile(values: np.ndarray, sigma_samples: float) -> np.ndarray:
    if len(values) < 3 or sigma_samples <= 0.1:
        return values.astype(np.float32)
    kernel_size = max(3, int(round(sigma_samples * 6.0)) | 1)
    maximum = len(values) if len(values) % 2 == 1 else len(values) - 1
    kernel_size = min(kernel_size, max(1, maximum))
    if kernel_size < 3:
        return values.astype(np.float32)
    return cv2.GaussianBlur(
        values.astype(np.float32).reshape(1, -1),
        (kernel_size, 1),
        sigmaX=sigma_samples,
    ).reshape(-1)


def _sample_edge_strip(
    observation: PieceObservation,
    edge_id: int,
    config: PatternConfig,
) -> EdgeFeature:
    edge = observation.piece.edges[edge_id]
    margin = min(config.endpoint_margin_mm, edge.length * 0.08)
    usable_length = max(config.sample_step_mm, edge.length - 2.0 * margin)
    sample_count = max(4, int(round(usable_length / config.sample_step_mm)) + 1)
    positions = np.linspace(margin, edge.length - margin, sample_count).astype(
        np.float32
    )
    # Dense samples next to the cut estimate the actual boundary colour. A
    # linear 0.7..5 mm grid compares points too far apart across a diagonal
    # stroke and can prefer a visually broken seam. Deeper rows remain present
    # for gradient/line-direction analysis.
    depth_fraction = np.linspace(0.0, 1.0, config.depth_samples) ** 2.0
    depths = (
        config.first_sample_depth_mm
        + depth_fraction * (config.strip_depth_mm - config.first_sample_depth_mm)
    ).astype(np.float32)

    dx = (edge.p2.x - edge.p1.x) / edge.length
    dy = (edge.p2.y - edge.p1.y) / edge.length
    # For a directed polygon boundary, a positive signed area means that the
    # interior is on the left of every edge. This also works for concave pieces.
    if signed_area(observation.piece.vertices) >= 0.0:
        normal_x, normal_y = -dy, dx
    else:
        normal_x, normal_y = dy, -dx

    along, inward = np.meshgrid(positions, depths)
    board_x = edge.p1.x + along * dx + inward * normal_x
    board_y = edge.p1.y + along * dy + inward * normal_y
    map_x = (
        board_x * observation.pixels_per_mm - observation.crop_origin_px[0]
    ).astype(np.float32)
    map_y = (
        board_y * observation.pixels_per_mm - observation.crop_origin_px[1]
    ).astype(np.float32)
    strip = cv2.remap(
        observation.texture_bgr,
        map_x,
        map_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )
    strip_mask = cv2.remap(
        observation.mask,
        map_x,
        map_y,
        cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    near_rows = min(3, config.depth_samples)
    valid = np.mean(strip_mask[:near_rows] > 0, axis=0) >= 0.67

    lab_strip = cv2.cvtColor(strip, cv2.COLOR_BGR2LAB).astype(np.float32)
    boundary_lab = np.median(lab_strip[:near_rows], axis=0)
    lightness = boundary_lab[:, 0] * (100.0 / 255.0)
    classes = np.zeros(sample_count, dtype=np.int8)
    classes[lightness < config.black_lightness_threshold] = 2
    red = (
        (boundary_lab[:, 1] >= config.red_a_threshold)
        & (lightness >= config.black_lightness_threshold)
    )
    classes[red] = 1

    gray_strip = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    # Only intensity variation along the edge indicates a stroke crossing the
    # seam. A card border parallel to the seam has a strong depth gradient but
    # provides no correspondence information and must not be rewarded.
    along_gradient = cv2.Sobel(
        gray_strip.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3
    )
    line_profile = np.clip(
        np.max(np.abs(along_gradient[: min(4, len(along_gradient))]), axis=0)
        / 320.0,
        0.0,
        1.0,
    )
    gray_boundary = np.median(gray_strip[:near_rows].astype(np.float32), axis=0)
    contrast = np.abs(np.gradient(gray_boundary)) / 80.0
    foreground = (classes != 0).astype(np.float32)
    information = np.clip(
        np.maximum(foreground, np.maximum(line_profile, contrast)), 0.0, 1.0
    )
    valid_lab = boundary_lab[valid]
    if len(valid_lab) >= 3:
        profile_variation = float(
            np.clip(
                np.std(valid_lab[:, 0]) / 45.0
                + np.std(valid_lab[:, 1]) / 35.0
                + np.mean(np.abs(np.gradient(gray_boundary[valid]))) / 45.0,
                0.0,
                1.0,
            )
        )
    else:
        profile_variation = 0.0
    # Uniform white, grey or solid-colour strips are weak evidence even when
    # their raw colours happen to agree in an incorrect assembly.
    information *= max(0.03, profile_variation)

    sigma_samples = config.profile_smoothing_mm / max(config.sample_step_mm, 1e-6)
    line_profile = _smooth_profile(line_profile, sigma_samples)
    information = _smooth_profile(information, sigma_samples)
    valid &= np.isfinite(boundary_lab).all(axis=1)
    information[~valid] = 0.0

    return EdgeFeature(
        edge_id=edge_id,
        positions_mm=positions,
        lab=boundary_lab,
        classes=classes,
        line_profile=np.clip(line_profile, 0.0, 1.0),
        information=np.clip(information, 0.0, 1.0),
        valid=valid,
    )


def build_edge_features(
    observation: PieceObservation,
    config: PatternConfig | None = None,
) -> PieceObservation:
    """Populate all cached edge profiles and return the same observation."""

    active = config or PatternConfig()
    observation.edge_features.clear()
    for edge in observation.piece.edges:
        observation.edge_features[edge.edge_id] = _sample_edge_strip(
            observation, edge.edge_id, active
        )
    (
        foreground,
        observation.red_ink_area_mm2,
        observation.black_ink_area_mm2,
    ) = _extract_foreground_mask(observation, active)
    (
        observation.corner_marker_scores,
        observation.corner_markers,
        observation.foreground_mask,
    ) = _extract_corner_markers(observation, active, foreground)
    return observation


def make_observation(
    piece: "Piece",
    rectified_bgr: np.ndarray,
    full_mask: np.ndarray,
    pixels_per_mm: float,
    config: PatternConfig | None = None,
    padding_mm: float = 2.0,
) -> PieceObservation:
    """Create a cropped observation from a calibrated full-board image."""

    from .models import Piece

    if not isinstance(piece, Piece):
        raise TypeError("piece must be a Piece")
    min_x, min_y, max_x, max_y = piece.bounds
    padding = int(round(padding_mm * pixels_per_mm))
    image_height, image_width = rectified_bgr.shape[:2]
    x0 = max(0, int(np.floor(min_x * pixels_per_mm)) - padding)
    y0 = max(0, int(np.floor(min_y * pixels_per_mm)) - padding)
    x1 = min(image_width, int(np.ceil(max_x * pixels_per_mm)) + padding + 1)
    y1 = min(image_height, int(np.ceil(max_y * pixels_per_mm)) + padding + 1)
    observation = PieceObservation(
        piece=piece,
        texture_bgr=rectified_bgr[y0:y1, x0:x1].copy(),
        mask=full_mask[y0:y1, x0:x1].copy(),
        crop_origin_px=(x0, y0),
        pixels_per_mm=pixels_per_mm,
    )
    return build_edge_features(observation, config)
