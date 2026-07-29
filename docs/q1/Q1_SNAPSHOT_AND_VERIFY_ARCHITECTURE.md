# Q1 Snapshot 初始规划与逐片复检架构

## 数据流

```text
PREVIEW（只取景/清晰度/曝光）
  → SPACE
INITIAL_CAPTURE（8帧中选最清晰高清帧）
  → INITIAL_ANALYZE（只执行一次完整识别）
  → PLAN_READY（固定P1/P2/P3/P4身份与目标）
  → [DryRun移动一块 → 单张VERIFY Snapshot → 决策] × 4
  → FINAL_VERIFY
  → COMPLETED
```

预览函数不调用完整 `pipeline`，预览候选数也不是 SPACE 的门槛。正式识别使用高清 Snapshot，标准化为 840×1188 的 A4 俯视图；当前工程的内部比例为4px/mm。

## 模块边界

- `snapshot_capture.py`：帧质量和突发抓图选择
- `paper_rectifier.py`：固定四角透视校正
- `piece_geometry.py`：粗顶点、边拟合、直线求交和毫米几何
- `initial_analyzer.py`：初始四块完整识别和固定模板匹配
- `plan_manager.py`：计划、版本和剩余源位姿更新
- `verification.py`：逐片/最终复检分类
- `snapshot_state.py`：状态转换和可恢复日志
- `snapshot_workflow.py`：纯DryRun编排

真实机械执行不在这些模块中。`DryRunExecutionAdapter`只记录二维建议，不导入或连接NexArm、STM32或电磁铁接口。
