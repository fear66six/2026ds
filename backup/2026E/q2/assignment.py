"""第二问：碎片分配结果（与第一问数据结构兼容，独立定义）"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


@dataclass
class PieceAssignment:
    detected_index: int
    template_name: str
    target_center_cm: Optional[Tuple[float, float]]
    target_angle_deg: float
    target_vertices_cm: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    match_score: float = 0.0
    vertex_error_cm: float = 0.0
