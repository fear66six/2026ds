# Q3 扑克牌拼图

Q3 复用 Q1 的 K230 取图、A4 检测、纸面到机械臂标定、NexArm 搬运流程和 STM32 电磁铁会话。与 Q1/Q2 不同的部分集中在扑克牌碎片检测、边缘与花纹匹配，以及拼图搜索。

正式流程先将横拍画面校正到竖向 A4 纸面坐标，再检测上半区的扑克牌碎片，求解后将完整牌面居中放入下半区。

求解器会在分割产生额外轮廓时对四片组合进行评分，并使用墙钟时间限制搜索。超时可以保留明确标记的 best-effort 结果用于诊断，但正式工作流不会为 best-effort 结果生成真实运动队列。

## 依赖

Q3 的依赖文件包含三套任务的公共运行依赖，并额外使用 Shapely：

```bash
cd ~/2026E
python3 -m pip install -r q3/requirements.txt
```

## 仅拍照与规划

```bash
cd ~/2026E
python3 -m q3.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

输出位于 `output/plans/q3/<timestamp>`，包含 `capture.png`、`plan.png`、`scene.json` 和 `piece_moves.json`。该命令不打开 NexArm 和 STM32 电磁铁串口。

## 完整执行

```bash
cd ~/2026E
python3 -m q3.main run \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --confirm RUN_Q3
```

完整执行会读取 `q1/config/robot_config.json` 中共享的 HOME、纸面到机械臂映射、接触面 Z 补偿、抓放高度、腕部映射、动作时序、串口和磁铁租约参数。Q3 不维护这些部署参数的副本。

## 事实边界

- 共享标定由 `q3/tests/test_q1_calibration_reuse.py` 进行离线契约测试；
- best-effort 结果的运动门禁由当前工作流源码确认；
- 实拍检测、花纹方向、机械可达性与最终拼放效果仍以 `docs/TODO_VERIFY.md` 的当前状态为准；
- 仓库里的配置值绑定历史样机，不能直接用于另一台设备。
