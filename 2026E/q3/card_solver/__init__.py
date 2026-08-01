"""Standalone Q3 playing-card fragment solver."""

from .config import PatternConfig, SolverConfig, production_solver_config
from .geometry import Point, RigidTransform
from .image_input import card_puzzle_from_rectified, load_card_puzzle
from .models import CardPuzzleInput, Piece, PieceObservation, Solution
from .solver import CardPuzzleSolver, SearchStats, calculate_pose

__all__ = [
    "CardPuzzleInput",
    "card_puzzle_from_rectified",
    "CardPuzzleSolver",
    "PatternConfig",
    "Piece",
    "PieceObservation",
    "Point",
    "RigidTransform",
    "SearchStats",
    "Solution",
    "SolverConfig",
    "production_solver_config",
    "calculate_pose",
    "load_card_puzzle",
]
