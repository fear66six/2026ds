# Q1 本地 ↔ Jetson 交接说明

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

- 唯一位姿字段：`home_pose = [168, 0, 230, -88, 1, 1]`
- **已删除**复位配置中的独立 `observe_pose`；正式 Q1 观察位也统一为同一 HOME（`runtime_config.observe_pose` / safety 的 `home_pose`）
- `position_tolerance_mm = 10.0`（用户在重复 HOME 实测后明确批准）
- 正式工作区、纸面到机械臂矩阵、腕部、高度、速度/加速度和到位判定均只从该文件读取
- 旧 HOME `[173,4,226,-84.4,0,0]` 在当前负载下重复停在 `[168,5,215,-88,1,1]`，且近邻重发无坐标/舵机变化。用户于 2026-07-30 选择 `[168,0,230,-88,1,1]` 作为 HOME；相对稳定反馈约 ΔY=5 mm、ΔZ=15 mm，若反馈不变将超过 10 mm 到位容差。这是项目目标调整，不代表 AT32 到舵机的执行故障已修复
- 正式抓放使用 `motion_mode=direct_pose`：只发送完整源 Z25 和完整目标 Z25，不生成固定 XY 升降或固定 Z 横移航点
- 运行 `20260729_153642_988359` 中操作者确认 Z25 方向发生了物理运动，但坐标/舵机反馈全程停在 HOME。正式配置因此保持 `direct_pick_release_pose_verified=false`；大行程命令后若新鲜反馈无变化，判为 `STALE_FEEDBACK_HARDWARE_FAULT` 并硬停，不得发送下一位姿或磁铁 ON
- STM32 电磁铁固定端点、500 ms 租约及吸合/释放等待也集中在该文件；生产 Q1 已固定为 `stm32`，`sim` 参数会被拒绝
- 刚体规划最大残差必须不超过 `vertex_max_error_mm=8.0`，否则以 `PLAN_GEOMETRY_RESIDUAL` 停止
- 当前自备纯色四片与题图模板为一致反面手性；第1问目标由 `q1/config/puzzle_geometry.py` 的 `TARGET_LAYOUT_MODE=mirror_x` 做整图镜像。单块变换仍禁止反射；扑克牌/现场未知碎片不得复用
- 正式抓放：`move_to_observe_pose` 已改为直接到 HOME，不再走 Z=200 下降路径
- 到位超时时不再发送运动，但会保存 `captures/home_timeout.jpg` 供构图调参
- 不要再把 HOME 直接设在 `workspace_limits` 边界上；软件范围必须比 HOME 略大

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

## 7. Q1 唯一正式闭环入口（2026-07-30）

旧的无确认分析、`RUN_Q1_HOME` 和 `RUN_Q1_ARM` 三档入口已删除。唯一令牌为
`RUN_Q1`；缺少精确令牌时在打开任何硬件前拒绝启动。

```bash
cd /home/jetson/2026E
python3 -m q1.main \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --max-cycles 4 \
  --confirm RUN_Q1
```

真实磁铁版本只在现场已确认供电、共地、MOSFET、续流保护和急停手段后使用：

```bash
python3 -m q1.main \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --max-cycles 4 \
  --confirm RUN_Q1
```

A4 四角像素由每帧 `detect_paper` 自动检测，不再使用 `paper_calibration.json`。

当前 HOME/观察位为 `(173,4,226,-84.4,0,0)`。曾尝试提高 15 mm 改善 A4
构图，但 Z241 实测未到位，现已回退。Z226 只表示 HOME 本身，不再作为转运高度。

目标闭环为：HOME（新鲜反馈确认）→ 拍照分析 → 审计 → 选一片 → 规划 →
一条完整 `set_pose` 从 HOME 插补到源 `(x,y,25,pitch,pick_roll,claw)` →
**源点新鲜反馈确认后**磁铁 ON 并读 STM32 状态 → 一条完整 `set_pose` 插补到目标
`(x,y,25,pitch,release_roll,claw)` → **目标新鲜反馈确认后**磁铁 OFF 并确认 →
回 HOME → 视觉复核 → 下一片。执行器不再发送分轴航点。陈旧/无法关联到本次
命令的反馈、到位超时或磁铁状态异常一律 `HARDWARE_FAULT`：磁铁安全关闭，
不发送恢复或后续位姿。遥测变化只记为 `FEEDBACK_CONFIRMED` /
`physical_evidence=UNPROVEN`，不得写成“已证明物理运动”。

当前配置为 `direct_pick_release_pose_verified=false`，在 flush 后的新鲜反馈
闭环于实机证明前，规划会保存但不会发送抓放位姿。生产 Q1 固定使用 STM32；
不写 `--magnet-backend` 时默认也是 `stm32`，传入 `sim` 会直接拒绝。STM32
使用 500 ms 看门狗租约，搬运期间每 250 ms 续租；续租失败、串口异常或状态
异常会停止后续位姿并尽力紧急断电。`physical_pick_enabled=true` 表示真实通电
路径已启用；首次动作后的下一轮视觉审计若将上一块判为 `PLACED_OK`，本次运行的
`physical_pick_verified` 才更新为 true，并写入 `physical_pick_verification.json`。

每条位姿命令写入独立 `motion_attempts`（目标、起始反馈、原始响应元数据、
样本、缓冲清理、时长、新鲜度判定、磁铁事件），成功与失败均落在
`output/runs/q1/<run_id>/` 的 `execution_result.json` / `events.jsonl` /
`failure.json`。

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
