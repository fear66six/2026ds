"""Render real fragment textures in solved poses and export PNG/GIF output."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import cv2
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from .geometry import Point, RigidTransform, interpolate_transform, normalize_angle
from .models import CardPuzzleInput, PieceObservation, PlacedPiece, Solution


def _source_pixel_to_board_mm(
    observation: PieceObservation,
    x: float,
    y: float,
) -> Point:
    return Point(
        (x + observation.crop_origin_px[0]) / observation.pixels_per_mm,
        (y + observation.crop_origin_px[1]) / observation.pixels_per_mm,
    )


def _affine_for_observation(
    observation: PieceObservation,
    transform: RigidTransform,
    output_pixels_per_mm: float,
    origin_mm: tuple[float, float],
) -> np.ndarray:
    source = np.asarray(((0, 0), (100, 0), (0, 100)), dtype=np.float32)
    destination = []
    for x, y in source:
        board_point = _source_pixel_to_board_mm(observation, float(x), float(y))
        world = transform.apply(board_point)
        destination.append(
            (
                (world.x - origin_mm[0]) * output_pixels_per_mm,
                (world.y - origin_mm[1]) * output_pixels_per_mm,
            )
        )
    return cv2.getAffineTransform(source, np.asarray(destination, dtype=np.float32))


def _composite_observation(
    canvas: np.ndarray,
    observation: PieceObservation,
    transform: RigidTransform,
    output_pixels_per_mm: float,
    origin_mm: tuple[float, float],
) -> None:
    height, width = canvas.shape[:2]
    affine = _affine_for_observation(
        observation, transform, output_pixels_per_mm, origin_mm
    )
    warped_texture = cv2.warpAffine(
        observation.texture_bgr,
        affine,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
    )
    warped_mask = cv2.warpAffine(
        observation.mask,
        affine,
        (width, height),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
    )
    canvas[warped_mask > 0] = warped_texture[warped_mask > 0]


def render_assembled_solution(
    observations: Iterable[PieceObservation],
    solution: Solution,
    *,
    pixels_per_mm: float = 5.0,
    margin_mm: float = 8.0,
) -> np.ndarray:
    """Return a cropped BGR image of the solved card rectangle."""

    if not solution.success or solution.rectangle is None:
        raise ValueError("a successful solution is required")
    observation_map = {item.piece.id: item for item in observations}
    min_x, min_y, max_x, max_y = solution.rectangle.bounds
    origin = (min_x - margin_mm, min_y - margin_mm)
    width = int(math.ceil((max_x - min_x + 2.0 * margin_mm) * pixels_per_mm))
    height = int(math.ceil((max_y - min_y + 2.0 * margin_mm) * pixels_per_mm))
    canvas = np.full((height, width, 3), 36, dtype=np.uint8)
    for placed in solution.placed_pieces:
        observation = observation_map.get(placed.piece_id)
        if observation is not None:
            _composite_observation(canvas, observation, placed.transform, pixels_per_mm, origin)

    rectangle_points = np.asarray(
        [
            (
                int(round((x - origin[0]) * pixels_per_mm)),
                int(round((y - origin[1]) * pixels_per_mm)),
            )
            for x, y in list(solution.rectangle.exterior.coords)[:-1]
        ],
        dtype=np.int32,
    )
    cv2.polylines(canvas, [rectangle_points], True, (30, 210, 30), 2, cv2.LINE_AA)
    for placed in solution.placed_pieces:
        contour = np.asarray(
            [
                (
                    int(round((point.x - origin[0]) * pixels_per_mm)),
                    int(round((point.y - origin[1]) * pixels_per_mm)),
                )
                for point in placed.vertices
            ],
            dtype=np.int32,
        )
        cv2.polylines(canvas, [contour], True, (70, 70, 70), 1, cv2.LINE_AA)
        centre = placed.centroid
        cv2.putText(
            canvas,
            str(placed.piece_id),
            (
                int(round((centre.x - origin[0]) * pixels_per_mm)),
                int(round((centre.y - origin[1]) * pixels_per_mm)),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (40, 180, 40),
            2,
            cv2.LINE_AA,
        )
    return canvas


def save_assembled_solution(
    path: str | Path,
    observations: Iterable[PieceObservation],
    solution: Solution,
    **kwargs: float,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = render_assembled_solution(observations, solution, **kwargs)
    if not cv2.imwrite(str(output), image):
        raise OSError(f"could not write image: {output}")
    return output


def _target_global_transform(
    puzzle: CardPuzzleInput,
    solution: Solution,
) -> RigidTransform:
    if solution.rectangle is None:
        raise ValueError("solution has no rectangle")
    coordinates = list(solution.rectangle.exterior.coords)[:-1]
    edges = [
        (
            math.dist(coordinates[index], coordinates[(index + 1) % 4]),
            coordinates[index],
            coordinates[(index + 1) % 4],
        )
        for index in range(4)
    ]
    _, first, second = max(edges, key=lambda item: item[0])
    long_angle = math.atan2(second[1] - first[1], second[0] - first[0])
    rotation = normalize_angle(math.pi / 2.0 - long_angle)
    rotation_transform = RigidTransform(rotation)
    transformed = [
        rotation_transform.apply(Point(float(x), float(y)))
        for x, y in coordinates
    ]
    centre_x = 0.5 * (min(point.x for point in transformed) + max(point.x for point in transformed))
    centre_y = 0.5 * (min(point.y for point in transformed) + max(point.y for point in transformed))
    paper_width, paper_height = puzzle.paper_size_mm
    if puzzle.layout == "left-right":
        target_centre = Point(0.5 * (puzzle.divider_mm + paper_width), paper_height / 2.0)
    else:
        target_centre = Point(paper_width / 2.0, 0.5 * (puzzle.divider_mm + paper_height))
    return RigidTransform(
        rotation,
        (target_centre.x - centre_x, target_centre.y - centre_y),
    )


def _blank_source_fragments(
    puzzle: CardPuzzleInput,
    moving_piece_ids: set[int],
) -> np.ndarray:
    background = puzzle.rectified_bgr.copy()
    if puzzle.layout == "left-right":
        destination = background[:, int(puzzle.divider_mm * puzzle.pixels_per_mm) :]
    else:
        destination = background[int(puzzle.divider_mm * puzzle.pixels_per_mm) :, :]
    median = np.median(destination.reshape(-1, 3), axis=0).astype(np.uint8)
    for observation in puzzle.observations:
        if observation.piece.id not in moving_piece_ids:
            continue
        x0, y0 = observation.crop_origin_px
        height, width = observation.mask.shape
        view = background[y0 : y0 + height, x0 : x0 + width]
        view[observation.mask > 0] = median
    return background


def render_board_solution(
    puzzle: CardPuzzleInput,
    solution: Solution,
) -> np.ndarray:
    """Render source fragments and the solved textured card on the A4 board."""

    if not solution.success:
        raise ValueError("a successful solution is required")
    canvas = puzzle.rectified_bgr.copy()
    observation_map = {item.piece.id: item for item in puzzle.observations}
    global_transform = _target_global_transform(puzzle, solution)
    for placed in solution.placed_pieces:
        _composite_observation(
            canvas,
            observation_map[placed.piece_id],
            global_transform.compose(placed.transform),
            puzzle.pixels_per_mm,
            (0.0, 0.0),
        )
    divider_px = int(round(puzzle.divider_mm * puzzle.pixels_per_mm))
    if puzzle.layout == "left-right":
        cv2.line(canvas, (divider_px, 0), (divider_px, len(canvas) - 1), (210, 210, 210), 2)
    else:
        cv2.line(canvas, (0, divider_px), (canvas.shape[1] - 1, divider_px), (210, 210, 210), 2)
    return canvas


def save_board_solution(
    path: str | Path,
    puzzle: CardPuzzleInput,
    solution: Solution,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), render_board_solution(puzzle, solution)):
        raise OSError(f"could not write image: {output}")
    return output


def save_board_animation(
    path: str | Path,
    puzzle: CardPuzzleInput,
    solution: Solution,
    *,
    frames_per_piece: int = 24,
    hold_frames: int = 12,
    duration_ms: int = 45,
    max_dimension_px: int = 1000,
) -> Path:
    """Animate each real fragment from its detected pose into the rectangle."""

    if not solution.success:
        raise ValueError("a successful solution is required")
    frames_per_piece = max(2, frames_per_piece)
    placed = list(solution.placed_pieces)
    background = _blank_source_fragments(
        puzzle, {item.piece_id for item in placed}
    )
    animation_scale = min(
        1.0,
        max_dimension_px / max(background.shape[:2]),
    )
    if animation_scale < 1.0:
        background = cv2.resize(
            background,
            None,
            fx=animation_scale,
            fy=animation_scale,
            interpolation=cv2.INTER_AREA,
        )
    animation_pixels_per_mm = puzzle.pixels_per_mm * animation_scale
    observation_map = {item.piece.id: item for item in puzzle.observations}
    global_transform = _target_global_transform(puzzle, solution)
    targets = {
        item.piece_id: global_transform.compose(item.transform) for item in placed
    }
    frames: list[Image.Image] = []
    for moving_index in range(len(placed)):
        for frame_index in range(frames_per_piece):
            fraction = frame_index / (frames_per_piece - 1)
            fraction = fraction * fraction * (3.0 - 2.0 * fraction)
            canvas = background.copy()
            for index, item in enumerate(placed):
                if index < moving_index:
                    transform = targets[item.piece_id]
                elif index == moving_index:
                    transform = interpolate_transform(
                        RigidTransform(), targets[item.piece_id], fraction
                    )
                else:
                    transform = RigidTransform()
                _composite_observation(
                    canvas,
                    observation_map[item.piece_id],
                    transform,
                    animation_pixels_per_mm,
                    (0.0, 0.0),
                )
            frames.append(Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)))
    frames.extend([frames[-1].copy() for _ in range(max(1, hold_frames))])
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=duration_ms,
        loop=0,
        optimize=False,
    )
    return output


def plot_solution(
    observations: Iterable[PieceObservation],
    solution: Solution,
):  # type: ignore[no-untyped-def]
    image = render_assembled_solution(observations, solution)
    figure, axis = plt.subplots(figsize=(7, 5))
    axis.imshow(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    axis.set_title(
        f"{solution.rectangle_width_mm:.1f} x {solution.rectangle_height_mm:.1f} mm"
    )
    axis.set_axis_off()
    figure.tight_layout()
    return figure, axis
