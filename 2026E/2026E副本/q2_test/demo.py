"""Run a complete solve and save or display its visualisation."""

from __future__ import annotations

import argparse

from puzzle_solver import PuzzleSolver
from puzzle_solver.sample_data import board_scattered_four_piece_rectangle
from puzzle_solver.visualization import save_board_animation, save_board_solution


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--debug", action="store_true", help="print DFS trace")
    parser.add_argument("--show", action="store_true", help="open the Matplotlib window")
    parser.add_argument(
        "--style",
        choices=("board", "analysis"),
        default="board",
        help="board scene or coordinate analysis plot (default: board)",
    )
    parser.add_argument(
        "--output",
        default="solution.png",
        help="output image path (default: solution.png)",
    )
    parser.add_argument(
        "--animate",
        action="store_true",
        help="also export one-piece-at-a-time assembly animation",
    )
    parser.add_argument(
        "--animation-output",
        default="board_solution.gif",
        help="GIF output path (default: board_solution.gif)",
    )
    parser.add_argument(
        "--frames-per-piece",
        type=int,
        default=28,
        help="animation frames for each moving piece",
    )
    arguments = parser.parse_args()

    pieces = board_scattered_four_piece_rectangle()
    solver = PuzzleSolver(debug=arguments.debug)
    solution = solver.solve(pieces)
    if not solution.success:
        print(solution.reason)
        return 1

    print(
        f"rectangle: {solution.rectangle_width_mm:.3f} x "
        f"{solution.rectangle_height_mm:.3f} mm"
    )
    for pose in solution.poses:
        print(
            f"piece={pose['piece_id']} x={pose['x']:.3f} y={pose['y']:.3f} "
            f"rotation={pose['rotation_deg']:.3f} deg"
        )
    if arguments.style == "board":
        output = save_board_solution(arguments.output, pieces, solution)
        if arguments.show:
            solver.plot_board_solution(pieces, solution, show=True)
    else:
        figure, _ = solver.plot_solution(solution, show=arguments.show)
        figure.savefig(arguments.output, dpi=160, bbox_inches="tight")
        output = arguments.output
    print(f"visualisation: {output}")
    if arguments.animate:
        animation_output = save_board_animation(
            arguments.animation_output,
            pieces,
            solution,
            frames_per_piece=arguments.frames_per_piece,
        )
        print(f"animation: {animation_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
