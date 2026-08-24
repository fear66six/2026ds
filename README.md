# 2026 年大学生电子设计竞赛 E 题：拼图装置

本仓库是 2026 年电赛 E 题“拼图装置”的完整工程实现。系统以 Jetson 为主控，
通过 K230 视觉模块获取工作区图像，完成 A4 纸面检测、碎片识别、拼图求解与坐标映射，
再控制 NexArm 机械臂和 STM32 电磁铁执行吸取、搬运与释放。

项目目前包含固定四片、随机几何碎片和扑克牌碎片三套任务流程，并提供仅规划模式、
完整执行模式、离线测试、运行记录和 Jetson 触控启动器。

> **安全提示**：`plan` 会访问相机，但不会打开 NexArm 或 STM32 串口；`run` 会产生
> 真实机械运动并控制电磁铁。未经现场确认，不要直接运行本文中的 `run` 命令，也不要
> 照搬仓库中的串口路径、标定值、位姿或安全范围。

## 任务实现

| 子任务 | 当前实现 | 入口 | 说明 |
|---|---|---|---|
| Q1 固定四片 | 检测四片同色碎片，按固定模板拼成目标矩形 | `q1.main` | 已形成单次拍照、一次规划、顺序执行的完整主链 |
| Q2 随机几何拼图 | 检测 1 至 4 片白色多边形，使用 DFS/回溯搜索矩形拼法 | `q2.main` | 仅精确且尺寸合规的结果会生成动作队列 |
| Q3 扑克牌拼图 | 检测扑克牌碎片，结合边缘和花纹特征求解 | `q3.main` | 超时的 best-effort 结果只用于诊断，不进入运动规划 |

Q1、Q2、Q3 共用 `2026E/q1/config/robot_config.json` 中的相机参数、纸面到机械臂
标定、抓放高度、腕部旋转映射、搬运时序和串口配置，避免三套任务产生相互冲突的
硬件参数副本。

## 系统流程

```text
K230 TTL 相机
    ↓ JPEG 图像
A4 检测与透视校正
    ↓ 210 mm × 297 mm 纸面坐标
碎片检测与拼图求解（Q1 / Q2 / Q3）
    ↓ PieceMove 动作队列
纸面坐标到机械臂坐标映射
    ↓
NexArm 搬运 ───── STM32 限时租约控制电磁铁
    ↓
运行图像、规划结果、场景数据与执行日志
```

完整执行采用“回 HOME → 单次拍照与规划 → 顺序抓放 → 最后回 HOME”的流程。
电磁铁控制使用限时租约并在异常和退出路径中强制关闭。

## 硬件组成

- Jetson 主控：运行 Python 视觉、规划与控制程序；当前精确模组、载板和 JetPack
  版本仍需以实机为准。
- Hiwonder K230 视觉模块：通过 TTL 请求式协议向 Jetson 返回 JPEG 图像。
- Hiwonder NexArm：由 Jetson 通过项目内 UART SDK 发送位姿命令。
- STM32F103VET6 电磁铁控制板：通过 USART 接收限时吸合、关闭和紧急关闭命令。
- MOSFET 驱动与电磁铁：实际型号、电气参数、输入极性和安全范围必须在通电前复核。

## 目录结构

```text
2026E/
├── q1/                         # 固定四片：视觉、规划、标定与公共硬件控制链
├── q2/                         # 随机白色多边形检测与矩形求解
├── q3/                         # 扑克牌碎片检测与拼图求解
├── drivers/k230_ttl_camera/    # K230 与 Jetson 两端的取图协议实现
├── hardware/nexarm/            # NexArm UART Python SDK
├── tools/                      # Jetson 触控启动器与桌面快捷方式
└── output/、runs/              # 规划结果、诊断数据与历史运行记录

drivers/                        # Jetson 侧 STM32 电磁铁驱动
firmware/                       # STM32F103C8T6/VET6 电磁铁固件与协议
tests/                          # 公共离线测试
docs/                           # 事实、决策、待验证事项与接口文档
tools/                          # 文档索引与离线辅助工具
TaskSuite_E/                    # 历史 K230/CanMV 工程，仅作项目参考
pintu/                          # 外部只读参考工程，不得修改或提交
```

## 环境准备

建议在 Jetson 的 Python 3 环境中，从正式工程目录安装依赖。Q3 的依赖文件包含三套
任务所需的公共运行依赖：

```bash
cd ~/2026E
python3 -m pip install -r q3/requirements.txt
```

主要 Python 依赖为 NumPy、OpenCV、pyserial 和 Shapely。安装后可先进行不会访问
硬件的导入检查：

```bash
python3 -c "import cv2, numpy, serial, shapely; print('runtime imports OK')"
```

## 使用方法

以下命令均在 Jetson 的 `~/2026E` 目录中执行。

### 1. 仅拍照与规划

`plan` 会初始化相机并保存识别与规划结果，但不会打开 NexArm 和 STM32 电磁铁串口。

```bash
# Q1：固定四片
python3 -m q1.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN

# Q2：随机白色多边形
python3 -m q2.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN

# Q3：扑克牌碎片
python3 -m q3.main plan \
  --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl \
  --confirm CAPTURE_AND_PLAN
```

规划输出写入 `output/plans/q1|q2|q3/<timestamp>/`，通常包含：

- `capture.png`：相机原图；
- `plan.png`：识别与目标位置叠加图；
- `scene.json`：检测和求解结果；
- `piece_moves.json`：待执行动作队列。

### 2. 完整执行

下面的命令会控制真实机械臂和电磁铁，只能在完成接线、串口、标定、运动范围和急停
准备的现场条件下使用。三个任务使用不同的精确确认令牌，防止误启动。

```bash
python3 -m q1.main run --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --magnet-backend stm32 --confirm RUN_Q1

python3 -m q2.main run --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --magnet-backend stm32 --confirm RUN_Q2

python3 -m q3.main run --robot-config q1/config/robot_config.json \
  --camera-backend k230_ttl --magnet-backend stm32 --confirm RUN_Q3
```

### 3. Jetson 触控界面

项目提供面向触控屏的 Q1/Q2/Q3 启动器，可选择任务并调整拼缝 Gap。安装桌面入口前应
先阅读脚本并确认 Jetson 上的工程路径：

```bash
cd ~/2026E
bash tools/install_jetson_desktop_launcher.sh
```

## 离线测试

测试不得访问真实串口或控制硬件。安装测试依赖后，可在仓库根目录执行：

```bash
python -m pytest -q
```

也可以只验证单个任务：

```bash
python -m pytest -q 2026E/q1/tests tests/q1
python -m pytest -q 2026E/q2/tests
python -m pytest -q 2026E/q3/tests
python -m pytest -q 2026E/drivers/k230_ttl_camera/tests
```

## 安全机制

- 模块导入和对象构造不应自动连接硬件；真实访问由执行入口显式触发。
- `plan` 与 `run` 分离，真实执行要求任务专属确认令牌。
- STM32 电磁铁采用超时租约和周期续租，异常退出时执行强制关闭。
- 运行参数集中在 `q1/config/robot_config.json`，修改后必须重新做离线检查和现场验证。
- 程序发完全部位姿并等待配置时长，不等于机械臂反馈已确认到位，也不等于最终拼放
  已通过视觉复核。
- 不要运行厂商 Demo、烧录固件、改设备树或操作 GPIO，除非已明确确认设备型号、接线
  与现场安全条件。

## 文档与事实来源

本 README 按“源码优先、原始资料优先”的规则整理。重要结论的主要来源如下：

| 结论 | 来源与定位 | 类型 | 可信等级 | 实机验证 |
|---|---|---|---|---|
| 赛题名称及 Q1 目标为四片拼成 10 cm × 6 cm 矩形 | `docs/PROJECT_FACTS.md`：F-001、F-012；其原始来源记为本地 `docs/E题_拼图装置.pdf` 第 1-2 页 | 项目事实对原始赛题的记录 | D（原 PDF 未纳入 Git） | 否 |
| Q1 的 plan/run 行为和确认令牌 | `2026E/q1/main.py`：`_build_parser`、`plan_once`、`build_controller`、`main` | 当前源码 | A | plan 需相机；run 需实机 |
| Q2 白色几何拼图与 Q1 控制链复用 | `2026E/q2/main.py`：`_build_parser`、`_build_runtime`、`build_controller` | 当前源码 | A | 最终抓放需实机 |
| Q3 扑克牌求解与 Q1 标定复用 | `2026E/q3/main.py`：`_build_parser`、`_build_runtime`、`build_controller` | 当前源码 | A | 实拍与抓放待继续验证 |
| K230 请求式 JPEG 链路 | `2026E/drivers/k230_ttl_camera/`；`docs/PROJECT_FACTS.md`：F-013 | 当前源码与实测记录 | A+D | 已有项目实测记录 |
| NexArm UART SDK 能力 | `2026E/hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py`：`NexArmClient` | 当前源码 | A | 当前端点仍以实机为准 |
| STM32 电磁铁限时租约和安全关闭 | `drivers/stm32_magnet_uart.py`；`firmware/stm32f103ve_uart_magnet/PROTOCOL.md` | 当前源码与固件协议 | A | 接线和负载仍须现场复核 |

原始赛题 PDF、厂商资料、安装包和其他大文件按仓库策略只保留在本地资料库，不随 Git
分发。克隆仓库后如需开展硬件开发，应先取得对应原件，再运行：

```bash
python tools/update_docs_index.py
python tools/search_docs.py "关键词"
```

进一步资料见：

- [Q1 实机调试说明](2026E/q1/README.md)
- [Q2 几何拼图说明](2026E/q2/README.md)
- [Q3 扑克牌拼图说明](2026E/q3/README.md)
- [项目资料导航](docs/README.md)
- [已确认事实](docs/PROJECT_FACTS.md)
- [工程决策](docs/DECISIONS.md)
- [待实机验证事项](docs/TODO_VERIFY.md)

## 项目状态说明

仓库中保留了历史运行与诊断记录，但这些记录只证明对应时间、配置和设备状态下的结果。
任何重新接线、重新标定、固件变更、机械结构调整或设备节点变化，都应视为新的现场条件，
重新完成相机、坐标映射、抓放高度、腕部方向、电磁铁与完整路径验证。
