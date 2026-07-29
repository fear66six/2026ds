# Q1 Snapshot DryRun 仿真指南

推荐命令：

```powershell
cd 2026E
python -m q1.main --image ..\backup\2026E\test.png --snapshot-plan --verify-after-each --simulate
```

摄像头模式：

```powershell
python -m q1.main --camera --camera-index 1 --snapshot-plan `
  --verify-after-each --simulate --save-all-debug
```

故障注入选项：

- `--simulate-piece-shift`
- `--simulate-place-offset`
- `--simulate-release-failure`
- `--simulate-camera-shift`

无故障DryRun会完成初始分析、四步计划、四次复检和最终复检。任何非PASS状态都会停止并给出原因。未启用 `--simulate` 时，SPACE仍会完成初始分析并保存JSON计划，但不会执行动作。

仿真执行器的 `is_hardware=False`，不会打开串口、Socket或发送电磁铁命令。
