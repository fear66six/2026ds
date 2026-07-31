# Q1 队友微调交接

你将拿到两份代码：

| 角色 | 路径 | 作用 |
|---|---|---|
| 本地仓库 | 开发机上的 `2026E/`（对方会把整份本地代码给你） | **改代码、看文档、离线测** |
| Jetson 实机 | `/home/jetson/2026E` | **真正跑硬件的唯一目录** |

原则：**本地是编辑源，Jetson 是运行源。** 本地改了会在 Jetson 执行的文件，必须同步到 Jetson，否则实机仍跑旧代码。

---

## 1. 登录 Jetson

实验室 USB 网（当前常用）：

```bash
ssh jetson@192.168.55.1
# 密码：yahboom（以现场为准）

cd /home/jetson/2026E
```

建议先确认串口还在：

```bash
ls -l /dev/serial/by-id/
```

三个设备不要混用：

| 设备 | by-id 路径（当前） | 常见节点 |
|---|---|---|
| NexArm | `...USB_Serial-if00-port0` | `ttyUSB0` |
| K230 相机 | `...5B7A028646-if00` | `ttyACM1` |
| STM32 电磁铁 | `...5B7A030191-if00` | `ttyACM0` |

配置文件：`/home/jetson/2026E/q1/config/robot_config.json`

---

## 2. Jetson 工程大致结构

```text
/home/jetson/2026E/
├── q1/                          # 第1问主程序（你主要改这里）
│   ├── main.py                  # CLI 入口：plan / run
│   ├── workflow.py              # 拍照 + 识别 + 规划（plan/run 共用）
│   ├── controller.py            # run：顺序执行 P1..P4 抓放
│   ├── analyzer.py              # 场景分析（纸面/碎片）
│   ├── motion.py                # PieceMove 规划、刚体变换
│   ├── magnet.py                # STM32 磁铁控制器（500ms 租约续租）
│   ├── geometry.py / pieces.py / puzzle_solver.py / wrist.py ...
│   ├── config/
│   │   └── robot_config.json    # ★ 微调优先改这里
│   ├── executors/
│   │   └── nexarm.py            # 机械臂执行（按时长推进，不靠陈旧反馈）
│   ├── camera/                  # K230 快照封装
│   ├── robot/safe_nexarm.py     # 安全封装
│   ├── scripts/                 # 复位/诊断脚本
│   └── tests/                   # 本地离线测试（Jetson 上可能不全）
├── drivers/
│   ├── k230_ttl_camera/         # K230 TTL 相机驱动
│   └── stm32_magnet_uart.py     # 电磁铁串口协议客户端
├── hardware/nexarm/.../nexarm_sdk.py   # NexArm SDK（实机事实）
├── requirements-q1.txt
└── output/runs/q1/<时间戳>/     # 每次运行产物
```

本地对应关系（把本地仓库根里的 `2026E/` 对齐到 Jetson 的 `~/2026E/`）：

| 本地 | Jetson |
|---|---|
| `.../2026E/q1/` | `/home/jetson/2026E/q1/` |
| `.../2026E/q1/config/robot_config.json` | `/home/jetson/2026E/q1/config/robot_config.json` |
| `.../2026E/drivers/` | `/home/jetson/2026E/drivers/` |
| `.../2026E/hardware/` | `/home/jetson/2026E/hardware/` |
| 仓库根 `docs/` | 一般不作为 Jetson 运行依赖；长期事实看本地 `docs/` |

仓库根还有固件：

- 旧板 C8T6：`firmware/stm32f103_uart_magnet/`（不要覆盖）
- 当前板 VET6：`firmware/stm32f103ve_uart_magnet/`（控制脚 **PC0**）

---

## 3. 程序怎么跑（当前正式流程）

工作目录必须是 `/home/jetson/2026E`：

### 只拍照规划（不动臂、不通电）

```bash
cd /home/jetson/2026E
python3 -m q1.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

产物：`capture.png`、`plan.png`、`scene.json`、`piece_moves.json`

### 完整抓放（真臂 + 真磁铁）

```bash
python3 -m q1.main run \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --magnet-backend stm32 \
  --confirm RUN_Q1
```

主流程：

```text
初始化相机 / NexArm / STM32
→ 发 HOME，等 move_duration_ms（当前 6000）
→ 单次拍照识别，生成 P1..P4 队列
→ 每片：到吸取位 → MAGNET_ON（续租）→ 到释放位 → MAGNET_OFF
→ 队列结束
```

运行目录会打印在终端：

```text
Q1_RUN_DIR=/home/jetson/2026E/output/runs/q1/<时间戳>
```

也可：

```bash
cd "$(cat /home/jetson/2026E/output/runs/q1/LATEST_RUN.txt)"
```

看结果优先：`final.json`、`scene.json`、`piece_moves.json`、`moves/0x_Px.json`、`events.jsonl`。

说明：`final.json` 里 `completed=true` 只表示**指令队列跑完**；`physical_pick_verified=false` 表示**还没证明吸住/拼好**。

---

## 4. 微调时优先动哪里

### A. 先改配置（最常见）

文件：`q1/config/robot_config.json`

| 字段 | 当前值 | 用途 |
|---|---|---|
| `home_pose` | `[175,0,210,-90,0,0]` | 观察/拍照位；拍不全 A4 时优先调这个 |
| `move_duration_ms` | `6000` | 每条位姿等待时间 |
| `pick_height` / `release_height` | `15` | 抓放高度 Z |
| `default_pitch_deg` | `-84.4` | 抓放俯仰 |
| `paper_to_robot_matrix` | 3×3 | 纸面 mm → 机械臂 XY |
| `wrist_roll_zero_deg` / `wrist_roll_sign` | `0` / `1` | 腕部滚转零位与方向 |
| `vertex_max_error_mm` | `8.0` | 规划刚体残差门限 |
| `magnet_lease_ms` | `500` | STM32 单次通电租约（续租保持吸合） |
| `magnet_settle_ms` | `200` | 吸合后等待 |

改完配置后同步到 Jetson，再跑。

### B. 视觉/规划效果不好

| 症状 | 先看 |
|---|---|
| 纸面识别差 | `analyzer.py`、`vision.py`、`white_segmentation.py` |
| 碎片顶点飘 | `edge_refinement.py`、`geometry.py` |
| 目标布局/镜像 | `config/puzzle_geometry.py`（当前 `TARGET_LAYOUT_MODE=mirror_x`） |
| 规划位姿怪 | `motion.py`、`wrist.py`、`COORDINATE_FRAMES.md` |
| 门限过严/过松 | `CORRECTION_STANDARDS.md` + `vertex_max_error_mm` |

### C. 机械臂动作

| 文件 | 作用 |
|---|---|
| `executors/nexarm.py` | 正式运动与时长推进 |
| `robot/safe_nexarm.py` | 安全封装 |
| `hardware/.../nexarm_sdk.py` | 厂商 SDK；改前先确认本地/Jetson 一致 |

注意：当前反馈常会陈旧，正式 `run` **按动作时长推进**，不是按反馈到位。

### D. 电磁铁

| 文件 | 作用 |
|---|---|
| `q1/magnet.py` | Q1 侧续租控制 |
| `drivers/stm32_magnet_uart.py` | 串口协议 |
| Jetson 实机 MCU | STM32F103VET6，GPIO **PC0** |

单次最长 500ms；搬运期间驱动会每约 250ms 续租。单独测电：

```bash
cd /home/jetson/2026E
export PORT=/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00
# 见近期交接：PING / GET_STATUS / 续租保持脚本
```

---

## 5. 同步到 Jetson（改完必做）

在开发机上把改过的文件拷到对应路径，例如：

```bash
# 示例：只同步配置
scp q1/config/robot_config.json jetson@192.168.55.1:/home/jetson/2026E/q1/config/robot_config.json
```

同步范围至少包括你改过的：

- `q1/**/*.py`
- `q1/config/**`
- `drivers/**`
- 若改了 SDK：`hardware/nexarm/**`

同步后在 Jetson 上快速校验：

```bash
cd /home/jetson/2026E
python3 -m json.tool q1/config/robot_config.json >/dev/null
python3 -m py_compile q1/main.py q1/controller.py q1/workflow.py
```

---

## 6. 安全红线

未经现场明确确认，不要：

- 发机械臂运动（任何 `set_pose` / `--confirm RUN_*`）
- 通电磁铁 / 接 MOSFET 乱试
- 烧录 STM32
- 假定 `/dev/ttyACM0` 一定是电磁铁（必须用 by-id）

建议顺序：

1. 只改配置 / 视觉，先 `plan`
2. 看 `plan.png` / `piece_moves.json` 合理后再 `run`
3. `run` 前清场、电磁铁悬空或确认负载安全

---

## 7. 建议阅读顺序

1. 本文（路径与结构）
2. `q1/README.md`（任务边界与入口）
3. `q1/config/robot_config.json`（当前参数）
4. `q1/COORDINATE_FRAMES.md`（坐标）
5. `q1/CORRECTION_STANDARDS.md`（识别/规划门限）
6. 仓库 `docs/PROJECT_FACTS.md`、`docs/DECISIONS.md`、`docs/TODO_VERIFY.md`（长期事实与待确认项）

---

## 8. 当前已知状态（2026-07-31）

- 本地与 Jetson 的 **Q1 运行代码已对齐**；差异主要是文档和部分本地测试文件。
- 已有完整 `run` 跑通记录（例：`20260731_012300_357937`）：队列跑完，但吸取/放置效果仍差，`physical_pick_verified=false`。
- 电磁铁 VET6 固件已烧录，协议可用；控制脚为 **PC0**。
- 微调重点通常是：HOME 构图、`paper_to_robot_matrix`、抓放高度/俯仰、视觉顶点、吸取可靠性。

> 一句话：在 Jetson 的 `/home/jetson/2026E` 跑；在本地改 `2026E/q1` 后务必同步；微调先动 `robot_config.json`，再动视觉/规划源码。
