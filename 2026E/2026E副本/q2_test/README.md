# Geometric rectangle puzzle solver

This directory is independent from the camera and robot code in the parent
project. Coordinates and configuration values are always in millimetres.

## Install and test

```powershell
cd q2_test
python -m pip install -r requirements.txt
python -m pytest
```

## Run the demo

```powershell
python demo.py --output solution.png
python demo.py --animate --animation-output board_solution.gif
python demo.py --debug --show
python demo.py --style analysis --output analysis.png
```

## Test a local Q2 image

The image adapter uses the standalone detector in
`puzzle_solver/raster_detection.py`, then passes millimetre vertices to the
DFS solver. The parent project's `q2` directory is not imported or required:

```powershell
python image_demo.py --image ..\q2_5.png --output q2_5_solved.png
python image_demo.py --image ..\q2_5.png --animate
```

The image solver automatically derives its edge-length tolerance from the
detected median edge. It supports both one-to-one interfaces and T-junctions
where multiple short edges cover one long open edge. Raster mode searches all
valid terminals until it reaches the configured raster-fit threshold.
Geometry-only calls retain strict defaults.

## Python API

```python
from puzzle_solver import Piece, PuzzleSolver

pieces = [
    Piece(0, [(0, 0), (50, 0), (50, 60), (0, 60)]),
    Piece(1, [(50, 0), (100, 0), (100, 60), (50, 60)]),
]

solver = PuzzleSolver(debug=False)
solution = solver.solve(pieces)
if solution.success:
    print(solution.poses)
    solver.plot_solution(solution, show=True)
else:
    print(solution.reason)
```

The solver fixes one scored base piece, derives all other rigid poses from
edge correspondences, and searches them with DFS, state copies and
backtracking. It never scales, reflects, or enumerates arbitrary poses.

The default demo uses the competition-board view: scattered fragments remain
above the horizontal divider, while the solved rectangle is centered below
it. Use `--style analysis` for the coordinate/connection diagnostic plot.
With `--animate`, pieces move one at a time using rigid translation and
rotation, and the complete sequence is exported as a GIF.
