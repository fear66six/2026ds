# Q1 本地 ↔ Jetson 交接说明

**队友微调请先看更短的 [TEAMMATE_HANDOFF.md](TEAMMATE_HANDOFF.md)。** 本文偏路径同步、历史状态与 AI 接手细节。

面向接手上的队友及其 AI：**先用本文定位路径与同步规则**，再回 `README.md` / `docs/` 查技术细节。

本文只保存在开发机本地仓库，**不要求同步到 Jetson**。

## 1. 两套根目录（必须先分清）

| 角色 | 路径 | 用途 |
|---|---|---|
| 本地开发机 | `D:\diansai\2026` | 改代码、查资料、写文档、离线测试 |
| Jetson 实机 | `/home/jetson/2026E` | **实际跑硬件的唯一工程根目录** |

对应关系（最常用）：

| 本地 | Jetson |
|---|---|
| `D:\diansai\2026\2026E\` | `/home/jetson/2026E/` |
| `D:\diansai\2026\2026E\q1\` | `/home/jetson/2026E\q1\` |
| `D:\diansai\2026\2026E\q1\config\robot_config.json` | `/home/jetson/2026E/q1/config/robot_config.json` |
| `D:\diansai\2026\2026E\q1\scripts\test_camera_arm_reset.py` | `/home/jetson/2026E/q1/scripts/test_camera_arm_reset.py` |
| `D:\diansai\2026\2026E\q1\robot\` | `/home/jetson/2026E/q1/robot/` |
| `D:\diansai\2026\2026E\drivers\k230_ttl_camera\` | `/home/jetson/2026E/drivers/k230_ttl_camera/`（以及历史兼容路径，见下） |
| `D:\diansai\2026\docs\` | 一般**不在 Jetson 上作为事实来源**；事实以本地 `docs/` + 实机报告为准 |

Jetson 登录（当前实验室 USB 网）：

```text
ssh jetson@192.168.55.1
工作目录：cd ~/2026E
```

Jetson 上旧路径多为兼容符号链接，真实内容已集中到：

```text
/home/jetson/2026E/hardware/
```

例如 NexArm SDK 运行时从：

```text
/home/jetson/2026E/hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py
```

加载；本地仓库对应路径通常是：

```text
D:\diansai\2026\2026E\hardware\nexarm\...
```

若本地尚无完整 `hardware/` 副本，以 Jetson 上该目录为实机事实，改 SDK 前先核对两边是否一致。

## 2. 强制同步规则（给人和 AI）

**本地改了会在 Jetson 上执行的逻辑，必须同步到 Jetson，否则队友/实机会跑旧代码。**

需要同步的典型文件：

- `2026E/q1/**/*.py`
- `2026E/q1/config/**`
- `2026E/q1/scripts/**`
- `2026E/drivers/**`（尤其 `k230_ttl_camera`）
- Jetson `hardware/` 下实际被 import 的 SDK/适配层

可不强制同步到 Jetson：

- 本交接文档 `HANDOFF.md`
- 本地 `docs/*.md` 决策/事实记录（但长期结论仍应写进本地 `docs/PROJECT_FACTS.md`、`DECISIONS.md`、`TODO_VERIFY.md`）
- 仅离线测试/缓存/报告

同步后至少做一次远端校验，例如：

```bash
# 在 Jetson 上
python3 -m json.tool ~/2026E/q1/config/robot_config.json
python3 -m py_compile ~/2026E/q1/scripts/test_camera_arm_reset.py
```

推荐流程：

1. 本地改代码 / 配置
2. 本地离线测试或语法检查
3. `scp`/`rsync` 到 `/home/jetson/2026E/...`
4. Jetson 上校验内容（JSON / `py_compile` / `grep`）
5. **无硬件令牌**先跑预检；只有用户明确确认后才运动

## 3. 当前复位测试状态（2026-07-30）

复位入口（Jetson）：

```bash
cd ~/2026E
python3 -m q1.scripts.test_camera_arm_reset
# 人工确认净空后：
python3 -m q1.scripts.test_camera_arm_reset --confirm RUN_ARM_RESET
```

当前 `robot_config.json` 要点：

- 唯一位姿字段：`home_pose = [175, 0, 210, -90, 0, 0]`
- **已删除**复位配置中的独立 `observe_pose`；正式 Q1 观察位也统一为同一 HOME（`runtime_config.observe_pose` / safety 的 `home_pose`）
- `position_tolerance_mm = 10.0`（用户在重复 HOME 实测后明确批准）
- 纸面到机械臂矩阵、腕部方向、高度和动作时间均只从该文件读取
- 旧 HOME `[173,4,226,-84.4,0,0]` 在当前负载下重复停在 `[168,5,215,-88,1,1]`，且近邻重发无坐标/舵机变化。项目曾按 D-029 使用 `[168,0,230,-88,1,1]`、按 D-034 使用 `[180,0,200,-90,0,0]`；用户于 2026-07-30 再按 D-036 将当前 HOME 改为 `[175,0,210,-90,0,0]` 以拍全纸张。配置修改本身不证明实机到位
- 正式抓放使用 `motion_mode=direct_pose`：只发送完整源 Z15 和完整目标 Z15，不生成固定 XY 升降或固定 Z 横移航点
- 串口打开并完成固件版本/当前位姿读取后，第一条控制器写命令就是 HOME `set_pose`；Q1 不再发送 `CMD_SET_GLOBAL_ACC`
- 运行 `20260729_153642_988359` 中操作者确认 Z25 方向发生了物理运动，但坐标/舵机反馈全程停在 HOME。该记录保留为历史故障证据；用户于 2026-07-30 进一步确认完整源/目标 Z15 六维位姿均已到位，当前 `direct_pick_release_pose_verified=true`
- 当前 NexArm 坐标与舵机反馈在已观察到的物理运动中仍会保持陈旧；正式 `run`
  不再用这组反馈控制流程，每条完整位姿发送后按 `move_duration_ms=6000` 推进
- STM32 电磁铁固定端点、500 ms 租约及吸合/释放等待也集中在该文件；生产 Q1 已固定为 `stm32`，`sim` 参数会被拒绝
- 刚体规划最大残差必须不超过 `vertex_max_error_mm=8.0`，否则以 `PLAN_GEOMETRY_RESIDUAL` 停止
- 当前自备纯色四片与题图模板为一致反面手性；第1问目标由 `q1/config/puzzle_geometry.py` 的 `TARGET_LAYOUT_MODE=mirror_x` 做整图镜像。单块变换仍禁止反射；扑克牌/现场未知碎片不得复用
- 正式抓放：`move_to_observe_pose` 已改为直接到 HOME，不再走 Z=200 下降路径
- 旧复位脚本仍是历史诊断入口，不再与 `q1.main plan` 串联作为正式流程

K230 固定口：

```text
/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A028646-if00  → 通常 ttyACM1
```

NexArm 稳定口（已实机出现过）：

```text
/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0  → 通常 ttyUSB0
```

STM32 电磁铁候选口（用户提供，运行前复核）：

```text
/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00
```

不要混用 K230、NexArm 和 STM32 三个串口。

## 4. AI 接手时优先打开的文件

| 目的 | 本地路径 |
|---|---|
| 本交接 / 路径映射 | `2026E/q1/HANDOFF.md` |
| Q1 调试总览 | `2026E/q1/README.md` |
| 唯一机械臂配置 | `2026E/q1/config/robot_config.json` |
| STM32 电磁铁驱动 | `drivers/stm32_magnet_uart.py`、`2026E/q1/magnet.py` |
| 复位脚本 | `2026E/q1/scripts/test_camera_arm_reset.py` |
| 安全封装 | `2026E/q1/robot/safe_nexarm.py` |
| 项目规则 | 仓库根 `AGENTS.md` |
| 长期事实 / 决策 / 待验证 | `docs/PROJECT_FACTS.md`、`docs/DECISIONS.md`、`docs/TODO_VERIFY.md` |
| 相机接口 | `docs/interfaces/k230_ttl_camera/` |

检索资料：

```text
python tools/search_docs.py "关键词"
```

## 5. 安全红线（不要让 AI 自行突破）

未经用户明确批准，不得：

- 打开真实串口 / 发送 NexArm 运动
- 通电磁铁 / MOSFET
- 烧录固件
- 把本地未同步的旧 Jetson 代码当最新真相

任何真实运动前：先无 `--confirm` 预检，再由人确认支架/线缆/工作区后使用 `RUN_ARM_RESET`。

## 6. 一句话提醒

> **本地是编辑源，Jetson 是运行源。改了本地可执行逻辑，就同步 Jetson；查路径先看本文件。**

## 7. Q1 视觉规划与完整执行入口（2026-07-30）

旧的无确认分析、`RUN_Q1_HOME` 和 `RUN_Q1_ARM` 三档入口已删除。当前分为：

- `plan` + `CAPTURE_AND_PLAN`：只打开 K230，单次拍照并生成完整规划，不初始化 NexArm/STM32。
- `run` + `RUN_Q1`：HOME、单次拍照规划、顺序执行完整抓放队列。

先同步 `q1/`、`drivers/k230_ttl_camera/` 和 `requirements-q1.txt`。当前可执行：

```bash
cd /home/jetson/2026E
python3 -m q1.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

该命令只生成时间戳目录中的 `capture.png`、`plan.png`、`scene.json` 和
`piece_moves.json`。`plan` 不检查真实抓放位姿验证标志。

完整抓放当前配置已通过 V-013 位姿门禁，使用：

```bash
python3 -m q1.main run \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --confirm RUN_Q1
```

缺少精确令牌、配置不完整或未来重新把
`direct_pick_release_pose_verified` 置为 `false` 时，`run` 在打开任何硬件前
拒绝启动。

A4 四角像素由初始桌面图像的 `detect_paper` 自动检测，不再使用
`paper_calibration.json`。主流程为：

```text
初始化相机 → 初始化 NexArm → 初始化 STM32
→ 发送 HOME/观察位并等待配置动作时长
→ 单次拍照、识别、拼图求解
→ 一次生成 P1..P4 PieceMove 队列
→ 逐项执行吸取、吸合、搬运、释放
→ 队列耗尽
```

每个 `PieceMove` 仍由完整刚体变换生成源/目标位置和腕部角度；执行器只发送
已配置的完整六维 `set_pose` 目标。源位姿的配置动作时长结束后磁铁 ON，目标
位姿的配置动作时长结束后磁铁 OFF。STM32 续租失败、磁铁状态异常或命令异常
仍会停止队列并关闭电磁铁。

生产 Q1 固定使用 STM32；不写 `--magnet-backend` 时默认也是 `stm32`，传入
`sim` 会直接拒绝。STM32 使用 500 ms 看门狗租约，搬运期间每 250 ms 续租。
`physical_pick_enabled=true` 只表示真实通电路径存在；单次观察流程不做动作后
视觉复核，因此不会在运行中把 `physical_pick_verified` 自动改成 true。

每条位姿命令写入独立 `motion_attempts`（目标、动作时长和时间完成状态）。
每次运行只拍一张正式图 `capture.png`，并输出 `plan.png`、`scene.json` 和
`piece_moves.json`；每片结果在 `moves/`，汇总为 `final.json` 或 `failure.json`。

运行目录创建后会立即在终端打印：

```text
Q1_RUN_ID=<时间戳>
Q1_RUN_DIR=/home/jetson/2026E/output/runs/q1/<时间戳>
Q1_RUN_EVENTS=.../events.jsonl
```

失败和退出时还会重复打印 `Q1_FAILED_RUN_DIR` / `Q1_LAST_RUN_DIR`。
最近一次目录始终写在 `output/runs/q1/LATEST_RUN.txt`，可执行：

```bash
cd "$(cat output/runs/q1/LATEST_RUN.txt)"
```

## 已废弃：独立单目标标定入口

`q1.scripts.calibrate_single_pose` 与 `single_pose_calibration` 配置块已删除。
保留的原始冲突证据仅为 Jetson
`output/runs/q1_pose_calibration/20260729_153642_988359/report.json`
（物理运动与陈旧 HOME 反馈并存）。正式闭环验证只走生产 Q1 执行器路径，
且须先完成无运动缓冲诊断，再经现场单独确认后做受控位姿闭环。
