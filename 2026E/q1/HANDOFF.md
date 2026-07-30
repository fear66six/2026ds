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
| `D:\diansai\2026\2026E\q1\config\arm_reset.json` | `/home/jetson/2026E/q1/config/arm_reset.json` |
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
python3 -m json.tool ~/2026E/q1/config/arm_reset.json
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

当前 `arm_reset.json` 要点：

- 唯一位姿字段：`home_pose = [173, 4, 226, -90, 0, 0]`
- **已删除**复位配置中的独立 `observe_pose`；正式 Q1 观察位也统一为同一 HOME（`runtime_config.observe_pose` / safety 的 `home_pose`）
- `position_tolerance_mm = 7.0`
- 软件范围（复位测试，HOME 不贴边）：`x [150,200]`，`y [-20,20]`，`z [200,250]`，`pitch [-95,-80]`；正式 safety 工作区仍由实机 JSON 填写
- XYZ 已验证可达；A4 旋转 90° 后完整入画，pitch=-90 的梯形改善效果待复测
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

不要把 K230 的 `ttyACM*` 当成机械臂口。

## 4. AI 接手时优先打开的文件

| 目的 | 本地路径 |
|---|---|
| 本交接 / 路径映射 | `2026E/q1/HANDOFF.md` |
| Q1 调试总览 | `2026E/q1/README.md` |
| 复位配置 | `2026E/q1/config/arm_reset.json` |
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
