# Q1 实机调试文档（主参考）

本目录文档是 **Q1 实机调试的主参考**。调参、对坐标、改容差时先看这里，再回源码核对。

| 文档 | 用途 |
|---|---|
| [TEAMMATE_HANDOFF.md](TEAMMATE_HANDOFF.md) | **队友微调交接**：Jetson 路径、目录结构、入口命令、调哪里 |
| [HANDOFF.md](HANDOFF.md) | 本地 ↔ Jetson 同步规则与更长状态记录（AI/深入接手） |
| [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md) | 参考坐标系、单位换算、标定 JSON、姿态映射 |
| [CORRECTION_STANDARDS.md](CORRECTION_STANDARDS.md) | 单次识别、队列规划门限与检查顺序 |
| [examples/](examples/) | 标定与安全参数 JSON 模板（数值须实机替换） |

## 任务边界（赛题）

- 来源：`docs/E题_拼图装置.pdf` 第 2 页图 2（可信等级 B）
- 四片同色碎片：上半区 → 下半区，拼成 **10 cm × 6 cm** 矩形
- 评分相关：相邻碎片对应顶点距离 ≤ **2 cm**（赛题评分）；代码内部规划门限更严，见 [CORRECTION_STANDARDS.md](CORRECTION_STANDARDS.md)

## 程序做什么

Q1 分成两个入口，但视觉和规划实现只有一份：

- `plan`：只初始化 K230，在机械臂当前观察位拍摄一张图，识别 A4 和四片碎片，
  生成完整 `PieceMove` 队列。不初始化 NexArm 或 STM32。
- `run`：初始化 K230、NexArm 和 STM32，发送 HOME 并等待动作时长结束后调用
  同一段单次拍照/规划流程，再顺序执行“到吸取位 → 吸合 → 搬运 → 到释放位 → 释放”。

数据流为：

```text
K230 TTL → SceneAnalyzer → plan_piece_moves
  ├─ plan：capture.png + plan.png + scene.json + piece_moves.json
  └─ run：NexArmRobotExecutor + STM32MagnetController
```

当前可在 Jetson 上执行的视觉规划命令（在 `2026E/` 下）：

```bash
python3 -m q1.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

机械臂标定完成后的完整命令：

```bash
python3 -m q1.main run \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --confirm RUN_Q1
```

A4 四角由本次桌面图像的 `detect_paper` 自动检测。`plan` 的时间戳目录只保存
原图 `capture.png`、规划叠加图 `plan.png`、`scene.json` 和
`piece_moves.json`，不生成 raw/scene/rectified/overlay/debug 图片树。机械臂与纸面映射参数只放在
`q1/config/robot_config.json`。

自备四片仍使用赛题图 2 的 100×60 mm 原始模板。当前固定实物根据运行
`20260731_012300_357937` 的四片检测面积配置 `target_scale=1.03`，实际规划
外包框约为 103×61.8 mm；目标原点 `(53.5,191.85) mm` 使其中心与 A4
下半区中心 `(105,222.75) mm` 重合。该比例只用于这套 Q1 四片。

Jetson Python 依赖列在 `requirements-q1.txt`：`numpy`、`cv2` 和 `pyserial`。
部署后可先做不访问设备的导入检查：

```bash
python3 -c "import cv2, numpy, serial; print('Q1 imports OK')"
```

`final.json` 的 `completed=true` 只表示所有位姿指令均已发送且配置动作时长结束，
不表示 NexArm 反馈确认到位，也不表示已经做过动作后的视觉复核。用户已于
2026-07-30 确认完整源/目标 Z15 六维位姿到位，
当前 `direct_pick_release_pose_verified=true`；`run` 仍要求精确的 `RUN_Q1`
令牌，`physical_pick_verified=false` 继续表示磁吸和最终拼放效果尚未验证。

## 证据类型约定

文档中统一标注：

- **源码确认**：以当前 `2026E/q1/*.py` 为准
- **赛题确认**：以 `docs/E题_拼图装置.pdf` 为准
- **工程决策**：项目主动选择，可改但要同步改代码与本文档
- **待实机验证**：当前不能当物理事实使用

## 安全

未经明确批准：不打开真实串口、不发送运动、不通电磁铁。  
示例 JSON 中的数字只是字段形状模板，**禁止原样用于真机运动**。
