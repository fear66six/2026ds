"""Solve polygons detected from a local Q2 image and render the board result."""

from __future__ import annotations

import argparse
from pathlib import Path

from puzzle_solver import PuzzleSolver
from puzzle_solver.image_input import image_solver_config, load_q2_image_pieces
from puzzle_solver.visualization import save_board_animation, save_board_solution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="local Q2 image path")
    parser.add_argument("--output", help="static PNG output path")
    parser.add_argument("--animate", action="store_true", help="also export a GIF")
    parser.add_argument("--animation-output", help="animation GIF output path")
    parser.add_argument("--debug", action="store_true", help="print DFS trace")
    parser.add_argument("--frames-per-piece", type=int, default=28)
    arguments = parser.parse_args()

    detected = load_q2_image_pieces(arguments.image)
    image_path = Path(arguments.image)
    output = Path(arguments.output) if arguments.output else image_path.with_name(
        f"{image_path.stem}_solved.png"
    )
    animation_output = (
        Path(arguments.animation_output)
        if arguments.animation_output
        else image_path.with_name(f"{image_path.stem}_solved.gif")
    )

    solver = PuzzleSolver(image_solver_config(detected.pieces), debug=arguments.debug)
    solution = solver.solve(detected.pieces)
    print(f"detected pieces: {len(detected.pieces)}")
    if not solution.success:
        print(solution.reason)
        return 1
    print(
        f"rectangle: {solution.rectangle_width_mm:.2f} x "
        f"{solution.rectangle_height_mm:.2f} mm"
    )
    save_board_solution(
        output,
        detected.pieces,
        solution,
        paper_size_mm=detected.paper_size_mm,
        divider_y_mm=detected.divider_y_mm,
    )
    print(f"visualisation: {output}")
    if arguments.animate:
        save_board_animation(
            animation_output,
            detected.pieces,
            solution,
            frames_per_piece=arguments.frames_per_piece,
            paper_size_mm=detected.paper_size_mm,
            divider_y_mm=detected.divider_y_mm,
        )
        print(f"animation: {animation_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

