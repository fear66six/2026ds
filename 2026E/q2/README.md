# Q2 白色纸片几何拼图

Q2 直接复用 Q1 的 K230 单次拍照、A4 检测与矫正、纸面到机械臂标定、
最大内接吸取点、NexArm transfer 流程和 STM32 电磁铁会话。Q2 只替换为
白色多边形碎片检测和矩形 DFS/回溯求解。

队友算法核心来自 `../../q2/puzzle_solver`。正式流程先由 Q1 把横拍画面矫正为
`210 x 297 mm` 的竖向纸面坐标，再检测上半区 1 至 4 片白色碎片；求解后的
矩形长边水平并居中放入下半区。只有非 `best_effort` 且尺寸符合赛题范围的
精确结果才会生成动作队列。

## 依赖

```bash
cd ~/2026E
python3 -m pip install -r q2/requirements.txt
```

## 只拍照和规划

```bash
cd ~/2026E
python3 -m q2.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

输出位于 `output/plans/q2/<timestamp>`，包含 `capture.png`、`plan.png`、
`scene.json` 和 `piece_moves.json`。该命令不打开 NexArm 和 STM32 磁铁串口。

## 完整执行

```bash
cd ~/2026E
python3 -m q2.main run \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --confirm RUN_Q2
```

完整执行会使用 `q1/config/robot_config.json` 中当前的 HOME、手眼矩阵、接触面
Z 补偿、吸放高度、roll 映射、摆臂补偿、动作时长、串口路径和磁铁续租参数，
Q2 内不保存这些参数的副本。

