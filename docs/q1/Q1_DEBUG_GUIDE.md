# Q1 Snapshot 调试与运行记录

每次运行目录：

```text
runs/q1/<run_id>/
├── run_config.json
├── initial_analysis.json
├── initial_plan.json
├── execution_log.jsonl
├── plan_versions/
├── captures/
├── debug/
└── final_result.json
```

初始调试图包括原图、透视图、二值图、轮廓、精细拟合边、模板匹配和计划图。逐片仿真生成 `verify_nn_raw/rectified/result` 以及 predictions、matches、errors 调试图；最终生成 raw、rectified、overlay 和结果JSON。

`execution_log.jsonl`记录时间、前后状态、模板、计划版本、图像、结果与原因。故障排查先看状态转换原因，再看对应Snapshot和候选拒绝原因。

注意：

- `KeyboardInterrupt`表示用户主动终止，不属于识别故障。
- 不用实时预览数字代替Snapshot结论。
- 不通过反复调HSV或面积阈值掩盖纸框、ROI或边界错误。
- 实机验证前保持DryRun，不连接机械臂或电磁铁。
