"""NexArm真实SDK适配层；实例化不连接，且不含虚构文本协议。"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path

import numpy as np

from ..models import ExecutionResult, RobotPose, SingleMovePlan
from ..runtime_config import Q1RuntimeConfig


SDK_RELATIVE_PATH = Path(
    "hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py"
)


class NexArmRobotExecutor:
    def __init__(self, project_root: Path, config: Q1RuntimeConfig) -> None:
        self.project_root = project_root
        self.config = config
        self.client = None
        self._last_pose: np.ndarray | None = None

    def initialize(self) -> None:
        blockers = self.config.real_run_blockers()
        if blockers:
            raise RuntimeError("; ".join(blockers))
        sdk_path = self.project_root / SDK_RELATIVE_PATH
        spec = importlib.util.spec_from_file_location("q1_nexarm_vendor_sdk", sdk_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"NexArm SDK无法加载: {sdk_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.client = module.NexArmClient(self.config.nexarm_port)
        self.client.open()

    def _move(self, pose: RobotPose) -> None:
        if self.client is None:
            raise RuntimeError("NexArm未初始化")
        if pose.duration_ms <= 0:
            raise RuntimeError("缺少经验证的动作持续时间")
        limits = self.config.workspace_limits or {}
        for axis, value in (("x", pose.x), ("y", pose.y), ("z", pose.z)):
            if axis not in limits or not limits[axis][0] <= value <= limits[axis][1]:
                raise RuntimeError(f"坐标越界或缺少{axis}工作区限制: {value}")
        self.client.set_pose(
            pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw, pose.duration_ms
        )
        self._last_pose = np.array([pose.x, pose.y, pose.z, pose.pitch, pose.roll, pose.claw])

    def move_to_observe_pose(self) -> None:
        values = self.config.observe_pose
        # 与复位 HOME 统一：单次直接到位拍照，不再使用 TaskSuite 的 Z=200 再下降路径。
        duration_ms = int(self.config.move_duration_ms or values[6])
        self._move(
            RobotPose(
                float(values[0]),
                float(values[1]),
                float(values[2]),
                float(values[3]),
                float(values[4]),
                float(values[5]),
                duration_ms,
            )
        )

    def wait_until_idle(self, timeout_s: float) -> bool:
        if self.client is None or self._last_pose is None:
            return False
        deadline = time.monotonic() + timeout_s
        stable = 0
        while time.monotonic() < deadline:
            current = self.client.get_current_coords(timeout=min(0.5, timeout_s))
            coords = np.asarray(current[:6], dtype=np.float64)
            stable = stable + 1 if np.linalg.norm(coords[:3] - self._last_pose[:3]) < 1.0 else 0
            if stable >= 2:
                return True
        return False

    def execute_single_move(self, plan: SingleMovePlan, magnet) -> ExecutionResult:
        required = (plan.approach_pose, plan.source_pose_robot, plan.transfer_pose, plan.release_pose)
        if any(pose is None for pose in required):
            return ExecutionResult(False, plan.template_id, "CALIBRATION_REQUIRED")
        # 以 pick_roll 到达源 → 吸取 → 抬升 → 在安全高度旋转到 release_roll → 搬运 → 下降释放
        self._move(plan.approach_pose)
        self._move(plan.source_pose_robot)
        with magnet.hold_session():
            if self.config.magnet_settle_ms is None:
                raise RuntimeError("缺少电磁铁吸合稳定时间")
            time.sleep(self.config.magnet_settle_ms / 1000.0)
            self._move(plan.approach_pose)
            if plan.rotate_pose is not None:
                self._move(plan.rotate_pose)
            self._move(plan.transfer_pose)
            self._move(plan.release_pose)
        self._move(plan.transfer_pose)
        return ExecutionResult(True, plan.template_id, "执行完成，等待视觉确认", False)

    def execute_release_recovery(self, plan: SingleMovePlan, attempt: int) -> ExecutionResult:
        if plan.release_pose is None or plan.transfer_pose is None or self.config.release_peel_delta is None:
            return ExecutionResult(False, plan.template_id, "CALIBRATION_REQUIRED: 释放恢复参数不完整")
        dx, dy, dz = self.config.release_peel_delta
        base = plan.release_pose
        peel = RobotPose(
            base.x + dx,
            base.y + dy,
            base.z + dz,
            base.pitch,
            base.roll,
            base.claw,
            base.duration_ms,
        )
        self._move(peel)
        self._move(plan.transfer_pose)
        return ExecutionResult(
            True,
            plan.template_id,
            f"已执行第{attempt}次经标定的释放侧移，等待视觉确认",
            False,
        )

    def emergency_stop(self) -> None:
        # 厂商Python SDK未暴露急停/扭矩关闭接口；关闭通信，硬件急停由上层门禁处理。
        if self.client is not None:
            self.client.close()
            self.client = None

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
