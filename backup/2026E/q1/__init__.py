"""
E题 第一问：自备 A4 + 图 2 四片纯色碎片

  检测 → 模板匹配 → 拼接规划 → (可选) 下位机执行 / 离线仿真
"""

from . import config
from .pipeline import run_pipeline

__all__ = ["config", "run_pipeline"]
