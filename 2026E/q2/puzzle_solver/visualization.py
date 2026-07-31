"""Matplotlib visualisation helpers for pieces and solutions."""

from __future__ import annotations

from collections.abc import Sequence
import math
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Polygon as MatplotlibPolygon
import numpy as np

from .geometry import RigidTransform
from .models import Piece, PlacedPiece, Solution, SolverState


def _axes(axes: Axes | None = None) -> tuple[Figure, Axes]:
    if axes is not None:
        return (axes.figure, axes)
    return plt.subplots(figsize=(9, 6))


def _finish_axes(axes: Axes, title: str) -> None:
    axes.set_aspect("equal", adjustable="datalim")
    axes.set_xlabel("x (mm)")
    axes.set_ylabel("y (mm)")
    axes.set_title(title)
    axes.grid(True, linewidth=0.4, alpha=0.35)
    axes.margins(0.12)


def _draw_placed(axes: Axes, placed_pieces: Sequence[PlacedPiece]) -> None:
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    for index, placed in enumerate(placed_pieces):
        color = colors[index % len(colors)]
        coordinates = list(placed.polygon.exterior.coords)
        xs = [coordinate[0] for coordinate in coordinates]
        ys = [coordinate[1] for coordinate in coordinates]
        axes.fill(xs, ys, color=color, alpha=0.42, linewidth=1.8, edgecolor=color)
        axes.scatter(xs[:-1], ys[:-1], color=color, s=24, zorder=4)
        center = placed.polygon.centroid
        axes.scatter([center.x], [center.y], color=color, marker="x", s=42, zorder=5)
        axes.text(
            center.x,
            center.y,
            f"  Piece {placed.piece_id}",
            ha="left",
            va="center",
            fontsize=9,
        )


def plot_pieces(
    pieces: Sequence[Piece],
    axes: Axes | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot input pieces in their supplied coordinate frames."""

    placed = [PlacedPiece.from_piece(piece, RigidTransform()) for piece in pieces]
    figure, axes = _axes(axes)
    _draw_placed(axes, placed)
    _finish_axes(axes, "Input pieces")
    if show:
        plt.show()
    return (figure, axes)


def plot_state(
    state: SolverState,
    axes: Axes | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot an intermediate DFS state and its open edges."""

    figure, axes = _axes(axes)
    _draw_placed(axes, state.placed_pieces)
    for edge in state.open_edges:
        axes.plot(
            [edge.p1.x, edge.p2.x],
            [edge.p1.y, edge.p2.y],
            linestyle=":",
            linewidth=1.4,
        )
    _finish_axes(axes, "DFS state (dotted edges are open)")
    if show:
        plt.show()
    return (figure, axes)


def plot_solution(
    solution: Solution,
    axes: Axes | None = None,
    show: bool = False,
) -> tuple[Figure, Axes]:
    """Plot pieces, IDs, vertices, centers, connections and final rectangle."""

    if not solution.success:
        raise ValueError("cannot plot an unsuccessful solution")
    figure, axes = _axes(axes)
    _draw_placed(axes, solution.placed_pieces)

    for connection in solution.connections:
        axes.plot(
            [connection.p1.x, connection.p2.x],
            [connection.p1.y, connection.p2.y],
            color="black",
            linestyle="--",
            linewidth=2.0,
            alpha=0.75,
        )
    if solution.rectangle is not None:
        coordinates = list(solution.rectangle.exterior.coords)
        axes.plot(
            [coordinate[0] for coordinate in coordinates],
            [coordinate[1] for coordinate in coordinates],
            color="black",
            linewidth=2.5,
            label="Final rectangle",
        )
        axes.legend(loc="best")
    _finish_axes(axes, "Solved rectangle")
    if show:
        plt.show()
    return (figure, axes)


def _board_solution_vertices(
    solution: Solution,
    target_center: tuple[float, float],
    long_axis: Literal["horizontal", "vertical"] = "horizontal",
) -> list[tuple[PlacedPiece, list[tuple[float, float]]]]:
    """Orient the assembly's long side and center it on the board."""

    if solution.rectangle is None:
        raise ValueError("solution does not contain a final rectangle")
    rectangle_coordinates = list(solution.rectangle.exterior.coords)[:-1]
    rectangle_edges = []
    for index, first in enumerate(rectangle_coordinates):
        second = rectangle_coordinates[(index + 1) % len(rectangle_coordinates)]
        dx = second[0] - first[0]
        dy = second[1] - first[1]
        rectangle_edges.append((math.hypot(dx, dy), math.atan2(dy, dx)))
    _, long_edge_angle = max(rectangle_edges, key=lambda item: item[0])
    if long_axis == "horizontal":
        target_long_edge_angle = 0.0
    elif long_axis == "vertical":
        target_long_edge_angle = math.pi / 2.0
    else:
        raise ValueError(f"unknown long-axis orientation: {long_axis}")
    rotation = target_long_edge_angle - long_edge_angle
    cos_angle = math.cos(rotation)
    sin_angle = math.sin(rotation)

    rotated: list[tuple[PlacedPiece, list[tuple[float, float]]]] = []
    all_coordinates: list[tuple[float, float]] = []
    for placed in solution.placed_pieces:
        coordinates = [
            (
                cos_angle * point.x - sin_angle * point.y,
                sin_angle * point.x + cos_angle * point.y,
            )
            for point in placed.vertices
        ]
        rotated.append((placed, coordinates))
        all_coordinates.extend(coordinates)

    min_x = min(coordinate[0] for coordinate in all_coordinates)
    max_x = max(coordinate[0] for coordinate in all_coordinates)
    min_y = min(coordinate[1] for coordinate in all_coordinates)
    max_y = max(coordinate[1] for coordinate in all_coordinates)
    translation = (
        target_center[0] - (min_x + max_x) / 2.0,
        target_center[1] - (min_y + max_y) / 2.0,
    )
    return [
        (
            placed,
            [
                (coordinate[0] + translation[0], coordinate[1] + translation[1])
                for coordinate in coordinates
            ],
        )
        for placed, coordinates in rotated
    ]


def plot_board_solution(
    input_pieces: Sequence[Piece],
    solution: Solution,
    axes: Axes | None = None,
    show: bool = False,
    paper_size_mm: tuple[float, float] = (210.0, 297.0),
    divider_y_mm: float | None = 148.5,
    divider_x_mm: float | None = None,
    layout: Literal["top-bottom", "left-right"] = "top-bottom",
    show_piece_ids: bool = False,
) -> tuple[Figure, Axes]:
    """Render input and assembly on opposite sides of the board divider.

    This matches the Q2 black-paper scene.  Input coordinates are expected in
    board millimetres.  The solved assembly only receives one additional
    global rotation and translation for display; individual piece shapes and
    scale remain unchanged.
    """

    if not solution.success:
        raise ValueError("cannot plot an unsuccessful solution")
    paper_width, paper_height = paper_size_mm
    if layout == "top-bottom":
        if divider_y_mm is None or not 0.0 < divider_y_mm < paper_height:
            raise ValueError("horizontal divider must lie inside the paper")
        target_center = (
            paper_width / 2.0,
            divider_y_mm + (paper_height - divider_y_mm) / 2.0,
        )
    elif layout == "left-right":
        if divider_x_mm is None or not 0.0 < divider_x_mm < paper_width:
            raise ValueError("vertical divider must lie inside the paper")
        target_center = (
            divider_x_mm + (paper_width - divider_x_mm) / 2.0,
            paper_height / 2.0,
        )
    else:
        raise ValueError(f"unknown board layout: {layout}")
    if axes is None:
        figure_height = 10.0
        figure_width = figure_height * paper_width / paper_height
        figure, axes = plt.subplots(figsize=(figure_width, figure_height))
    else:
        figure = axes.figure

    figure.patch.set_facecolor("black")
    axes.set_facecolor("black")
    axes.set_position([0.0, 0.0, 1.0, 1.0])

    def draw_polygon(
        coordinates: Sequence[tuple[float, float]],
        piece_id: int,
        outline: str,
    ) -> None:
        xs = [coordinate[0] for coordinate in coordinates]
        ys = [coordinate[1] for coordinate in coordinates]
        axes.fill(xs, ys, facecolor="white", edgecolor=outline, linewidth=1.15)
        if show_piece_ids:
            axes.text(
                sum(xs) / len(xs),
                sum(ys) / len(ys),
                str(piece_id),
                color="black",
                ha="center",
                va="center",
                fontsize=9,
                weight="bold",
            )

    for piece in input_pieces:
        draw_polygon(
            [point.as_tuple() for point in piece.vertices],
            piece.id,
            outline="#b0b0b0",
        )

    solved_polygons = _board_solution_vertices(
        solution,
        target_center,
        long_axis="vertical" if layout == "left-right" else "horizontal",
    )
    solved_xs = [x for _, coordinates in solved_polygons for x, _ in coordinates]
    solved_ys = [y for _, coordinates in solved_polygons for _, y in coordinates]
    outside_paper = (
        min(solved_xs) < 0
        or max(solved_xs) > paper_width
        or min(solved_ys) < 0
        or max(solved_ys) > paper_height
    )
    wrong_side = (
        min(solved_ys) <= divider_y_mm
        if layout == "top-bottom" and divider_y_mm is not None
        else min(solved_xs) <= divider_x_mm
        if divider_x_mm is not None
        else True
    )
    if outside_paper or wrong_side:
        raise ValueError("solved rectangle does not fit in the target region")
    rectangle_outline = plt.Rectangle(
        (min(solved_xs), min(solved_ys)),
        max(solved_xs) - min(solved_xs),
        max(solved_ys) - min(solved_ys),
        fill=False,
        edgecolor="#707070",
        linewidth=1.2,
        zorder=1,
    )
    axes.add_patch(rectangle_outline)
    for placed, coordinates in solved_polygons:
        draw_polygon(coordinates, placed.piece_id, outline="black")

    if layout == "top-bottom":
        assert divider_y_mm is not None
        axes.plot(
            [0.0, paper_width],
            [divider_y_mm, divider_y_mm],
            color="white",
            linewidth=2.5,
            solid_capstyle="butt",
        )
    else:
        assert divider_x_mm is not None
        axes.plot(
            [divider_x_mm, divider_x_mm],
            [0.0, paper_height],
            color="white",
            linewidth=2.5,
            solid_capstyle="butt",
        )
    axes.set_xlim(0.0, paper_width)
    axes.set_ylim(paper_height, 0.0)
    axes.set_aspect("equal", adjustable="box")
    axes.axis("off")
    if show:
        plt.show()
    return (figure, axes)


def save_board_solution(
    path: str | Path,
    input_pieces: Sequence[Piece],
    solution: Solution,
    dpi: int = 140,
    **kwargs,
) -> Path:
    """Save a board-style result without axes or surrounding whitespace."""

    figure, _ = plot_board_solution(input_pieces, solution, **kwargs)
    output = Path(path)
    figure.savefig(
        output,
        dpi=dpi,
        facecolor="black",
        bbox_inches=None,
        pad_inches=0,
    )
    return output


def _rigid_motion_between_vertices(
    source: Sequence[tuple[float, float]],
    target: Sequence[tuple[float, float]],
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return source center, target center and no-reflection rotation angle."""

    source_array = np.asarray(source, dtype=float)
    target_array = np.asarray(target, dtype=float)
    if source_array.shape != target_array.shape or len(source_array) < 3:
        raise ValueError("source and target polygons must have matching vertices")
    source_center = source_array.mean(axis=0)
    target_center = target_array.mean(axis=0)
    source_centered = source_array - source_center
    target_centered = target_array - target_center
    covariance = source_centered.T @ target_centered
    left, _, right_transposed = np.linalg.svd(covariance)
    rotation = right_transposed.T @ left.T
    if np.linalg.det(rotation) < 0:
        right_transposed[-1, :] *= -1.0
        rotation = right_transposed.T @ left.T
    angle = math.atan2(float(rotation[1, 0]), float(rotation[0, 0]))
    return (source_center, target_center, angle)


def animate_board_solution(
    input_pieces: Sequence[Piece],
    solution: Solution,
    frames_per_piece: int = 28,
    hold_frames: int = 12,
    interval_ms: int = 40,
    paper_size_mm: tuple[float, float] = (210.0, 297.0),
    divider_y_mm: float | None = 148.5,
    divider_x_mm: float | None = None,
    layout: Literal["top-bottom", "left-right"] = "top-bottom",
    show_piece_ids: bool = False,
    repeat: bool = True,
) -> tuple[Figure, FuncAnimation]:
    """Animate pieces moving one at a time into the solved rectangle.

    Every frame is computed from a rotation and center translation.  The
    Kabsch fit explicitly rejects reflection and does not estimate scale.
    """

    if not solution.success:
        raise ValueError("cannot animate an unsuccessful solution")
    if frames_per_piece < 2:
        raise ValueError("frames_per_piece must be at least two")
    if hold_frames < 0:
        raise ValueError("hold_frames must be non-negative")

    paper_width, paper_height = paper_size_mm
    if layout == "top-bottom":
        if divider_y_mm is None or not 0.0 < divider_y_mm < paper_height:
            raise ValueError("horizontal divider must lie inside the paper")
        target_center = (
            paper_width / 2.0,
            divider_y_mm + (paper_height - divider_y_mm) / 2.0,
        )
    elif layout == "left-right":
        if divider_x_mm is None or not 0.0 < divider_x_mm < paper_width:
            raise ValueError("vertical divider must lie inside the paper")
        target_center = (
            divider_x_mm + (paper_width - divider_x_mm) / 2.0,
            paper_height / 2.0,
        )
    else:
        raise ValueError(f"unknown board layout: {layout}")
    target_polygons = {
        placed.piece_id: coordinates
        for placed, coordinates in _board_solution_vertices(
            solution,
            target_center,
            long_axis="vertical" if layout == "left-right" else "horizontal",
        )
    }
    source_by_id = {piece.id: piece for piece in input_pieces}
    ordered_ids = [placed.piece_id for placed in solution.placed_pieces]
    if set(ordered_ids) != set(source_by_id):
        raise ValueError("input pieces do not match the solution")

    motions: dict[int, tuple[np.ndarray, np.ndarray, float, np.ndarray]] = {}
    for piece_id in ordered_ids:
        source_coordinates = [
            point.as_tuple() for point in source_by_id[piece_id].vertices
        ]
        target_coordinates = target_polygons[piece_id]
        source_center, target_piece_center, angle = _rigid_motion_between_vertices(
            source_coordinates,
            target_coordinates,
        )
        source_local = np.asarray(source_coordinates, dtype=float) - source_center
        motions[piece_id] = (
            source_center,
            target_piece_center,
            angle,
            source_local,
        )

    figure_height = 10.0
    figure_width = figure_height * paper_width / paper_height
    figure, axes = plt.subplots(figsize=(figure_width, figure_height))
    figure.patch.set_facecolor("black")
    axes.set_facecolor("black")
    axes.set_position([0.0, 0.0, 1.0, 1.0])
    if layout == "top-bottom":
        assert divider_y_mm is not None
        axes.plot(
            [0.0, paper_width],
            [divider_y_mm, divider_y_mm],
            color="white",
            linewidth=2.5,
            solid_capstyle="butt",
            zorder=20,
        )
    else:
        assert divider_x_mm is not None
        axes.plot(
            [divider_x_mm, divider_x_mm],
            [0.0, paper_height],
            color="white",
            linewidth=2.5,
            solid_capstyle="butt",
            zorder=20,
        )

    all_target_coordinates = [
        coordinate for coordinates in target_polygons.values() for coordinate in coordinates
    ]
    target_min_x = min(coordinate[0] for coordinate in all_target_coordinates)
    target_max_x = max(coordinate[0] for coordinate in all_target_coordinates)
    target_min_y = min(coordinate[1] for coordinate in all_target_coordinates)
    target_max_y = max(coordinate[1] for coordinate in all_target_coordinates)
    target_hint = plt.Rectangle(
        (target_min_x, target_min_y),
        target_max_x - target_min_x,
        target_max_y - target_min_y,
        fill=False,
        edgecolor="#404040",
        linewidth=1.0,
        zorder=1,
    )
    axes.add_patch(target_hint)

    patches: dict[int, MatplotlibPolygon] = {}
    labels = []
    for piece_id in ordered_ids:
        source_coordinates = [
            point.as_tuple() for point in source_by_id[piece_id].vertices
        ]
        patch = MatplotlibPolygon(
            source_coordinates,
            closed=True,
            facecolor="white",
            edgecolor="#b0b0b0",
            linewidth=1.15,
            zorder=4,
        )
        axes.add_patch(patch)
        patches[piece_id] = patch
        if show_piece_ids:
            center = np.asarray(source_coordinates, dtype=float).mean(axis=0)
            label = axes.text(
                center[0],
                center[1],
                str(piece_id),
                color="black",
                ha="center",
                va="center",
                fontsize=9,
                weight="bold",
                zorder=25,
            )
            labels.append((piece_id, label))

    axes.set_xlim(0.0, paper_width)
    axes.set_ylim(paper_height, 0.0)
    axes.set_aspect("equal", adjustable="box")
    axes.axis("off")

    total_frames = hold_frames * 2 + frames_per_piece * len(ordered_ids)

    def piece_progress(frame_index: int, order_index: int) -> float:
        start = hold_frames + order_index * frames_per_piece
        progress = (frame_index - start) / (frames_per_piece - 1)
        progress = min(1.0, max(0.0, progress))
        return progress * progress * (3.0 - 2.0 * progress)

    def update(frame_index: int):  # type: ignore[no-untyped-def]
        artists = [target_hint, *patches.values()]
        centers: dict[int, np.ndarray] = {}
        for order_index, piece_id in enumerate(ordered_ids):
            progress = piece_progress(frame_index, order_index)
            source_center, target_piece_center, angle, source_local = motions[piece_id]
            current_angle = angle * progress
            cos_angle = math.cos(current_angle)
            sin_angle = math.sin(current_angle)
            rotation = np.array(
                [[cos_angle, -sin_angle], [sin_angle, cos_angle]],
                dtype=float,
            )
            current_center = source_center + progress * (
                target_piece_center - source_center
            )
            current_vertices = source_local @ rotation.T + current_center
            patch = patches[piece_id]
            patch.set_xy(current_vertices)
            patch.set_edgecolor("black" if progress >= 1.0 else "#b0b0b0")
            patch.set_zorder(10 if 0.0 < progress < 1.0 else 4 + order_index)
            centers[piece_id] = current_center
        for piece_id, label in labels:
            label.set_position(centers[piece_id])
            artists.append(label)
        return artists

    animation = FuncAnimation(
        figure,
        update,
        frames=total_frames,
        interval=interval_ms,
        blit=True,
        repeat=repeat,
    )
    return (figure, animation)


def save_board_animation(
    path: str | Path,
    input_pieces: Sequence[Piece],
    solution: Solution,
    fps: int = 24,
    dpi: int = 80,
    **kwargs,
) -> Path:
    """Export the board assembly animation as a GIF."""

    output = Path(path)
    if output.suffix.lower() != ".gif":
        raise ValueError("board animation output must use the .gif extension")
    figure, animation = animate_board_solution(input_pieces, solution, **kwargs)
    animation.save(output, writer=PillowWriter(fps=fps), dpi=dpi)
    plt.close(figure)
    return output
