"""只含 Q1 闭环运行配置；未知实机参数保持为空。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Q1RuntimeConfig:
    mode: str = "simulate"
    camera_index: int = 0
    capture_burst: int = 8
    settle_time_ms: int = 200
    max_visual_retries: int = 2
    max_release_retries: int = 2
    max_cycles: int = 16
    place_center_tolerance_mm: float = 5.0
    place_angle_tolerance_deg: float = 5.0
    vertex_max_error_mm: float = 8.0
    remaining_move_tolerance_mm: float = 3.0
    remaining_rotate_tolerance_deg: float = 3.0
    target_origin_mm: tuple[float, float] = (55.0, 168.5)
    paper_calibration: Path | None = None
    arm_calibration: Path | None = None
    run_root: Path = Path("runs/q1")
    nexarm_port: str | None = None
    magnet_port: str | None = None

    # TaskSuite_E/board_roi_config.h + system_task_handle.cpp::move_observe().
    observe_pose: tuple[float, float, float, float, float, float, int] = (
        200.0,
        0.0,
        160.0,
        -90.0,
        0.0,
        -60.0,
        1500,
    )

    # 下列实机安全参数没有可直接复用的视觉到机械臂标定，禁止伪造默认值。
    safe_height: float | None = None
    pick_height: float | None = None
    release_height: float | None = None
    move_duration_ms: int | None = None
    magnet_settle_ms: int | None = None
    release_peel_delta: tuple[float, float, float] | None = None
    workspace_limits: dict[str, tuple[float, float]] | None = None

    def real_run_blockers(self) -> list[str]:
        blockers: list[str] = []
        if self.arm_calibration is None or not self.arm_calibration.exists():
            blockers.append("CALIBRATION_REQUIRED: 缺少A4到机械臂坐标标定")
        if self.paper_calibration is None or not self.paper_calibration.exists():
            blockers.append("CALIBRATION_REQUIRED: 缺少A4四角标定")
        if not self.nexarm_port:
            blockers.append("缺少NexArm端口")
        if not self.magnet_port:
            blockers.append("缺少STM32电磁铁端口")
        if self.safe_height is None:
            blockers.append("缺少安全高度")
        if self.pick_height is None:
            blockers.append("缺少抓取高度")
        if self.release_height is None:
            blockers.append("缺少释放高度")
        if self.move_duration_ms is None:
            blockers.append("缺少单步动作持续时间")
        if self.magnet_settle_ms is None:
            blockers.append("缺少电磁铁吸合稳定时间")
        if self.release_peel_delta is None:
            blockers.append("缺少释放侧移方向与距离")
        if not self.workspace_limits:
            blockers.append("缺少机械臂工作区边界")
        return blockers
