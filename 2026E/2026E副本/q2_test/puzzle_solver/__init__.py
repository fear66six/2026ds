"""Public API for the two-dimensional rectangle puzzle solver."""

from .config import SolverConfig
from .geometry import Point, RigidTransform
from .models import Edge, Piece, PlacedPiece, Solution
from .solver import PuzzleSolver, SearchStats, calculate_pose, score_base_piece

__all__ = [
    "Edge",
    "Piece",
    "PlacedPiece",
    "Point",
    "PuzzleSolver",
    "RigidTransform",
    "SearchStats",
    "Solution",
    "SolverConfig",
    "calculate_pose",
    "score_base_piece",
]

