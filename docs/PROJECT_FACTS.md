# 已确认的长期项目事实

这里只记录可追溯且适用范围明确的事实。API 全集、协议全文和易变参数不在此复制。

## F-001 项目的原始赛题为 2026 赛区 E 题“拼图装置”

- 结论：项目资料中保存的赛题原文标题为“2026 年全国大学生电子设计竞赛赛区赛（TI 杯）暨模拟电子系统设计专题赛选拔赛赛题”，E 题名称为“拼图装置”。
- 来源：`docs/E题_拼图装置.pdf`
- 来源位置：第 1 页标题及“一、任务”
- 可信等级：B（正式赛题 PDF）
- 适用范围：项目任务边界
- 最后核查时间：2026-07-29
- 备注：第 1 页已渲染视觉核查；具体尺寸和评分要求应在相关开发任务中重读全部 3 页。

## F-002 项目资料包含 NexArm UART Python 客户端实现

- 结论：随资料提供的 UART SDK 定义 `NexArmClient`；构造签名为 `__init__(self, port, baudrate=1000000, timeout=0.1, write_timeout=0.1)`，`set_pose` 签名为 `set_pose(self, x, y, z, pitch, roll, claw, duration_ms)`。构造函数不打开串口，`open()` 或首次需要串口的方法才会创建 `serial.Serial`。
- 来源：`docs/NexArm机械臂/1.教程资料/6. 外部主控二次开发/02 程序源码/UART_Control/nexarm_sdk.py`
- 来源位置：`NexArmClient`，第 79-114 行；`set_pose`，第 296-306 行
- 可信等级：A（实际 Python SDK 源码）
- 适用范围：该仓库内这份 UART SDK；不证明当前串口节点、物理单位或实机固件兼容性
- 最后核查时间：2026-07-29
- 备注：`docs/_nexarm_extract/UART_Control/nexarm_sdk.py` 是便捷副本，不作为更高等级来源。

## F-003 项目资料中的 NexArm SDK 同时提供 UART 与 Wi-Fi 传输实现

- 结论：UART 版本定义 `NexArmClient`，Wi-Fi 版本定义 `NexArmWiFiClient`；两者源码均实现帧构造、校验、收包和请求逻辑。Wi-Fi 源码的默认地址只是该示例实现的默认值，不是当前设备地址。
- 来源：`docs/NexArm机械臂/1.教程资料/6. 外部主控二次开发/02 程序源码/UART_Control/nexarm_sdk.py`；`docs/NexArm机械臂/1.教程资料/6. 外部主控二次开发/02 程序源码/WiFi_Control.zip!/nexarm_wifi_sdk.py`
- 来源位置：UART 的 `build_frame`/`read_packet`/`request`（第 117-229 行）；Wi-Fi 的 `NexArmWiFiClient`（第 78-109 行）
- 可信等级：A（实际 Python SDK 源码）
- 适用范围：仓库所含 SDK 能力，不代表项目已经选定通信方式
- 最后核查时间：2026-07-29
- 备注：不得把固件命令候选自动写成 Python SDK 已实现方法。

## F-004 NexArm 图纸资料包含一份 V1.0 的 NexArm-ESP32 控制器原理图

- 结论：原理图标题栏标注“幻尔科技有限公司”“NexArm控制器原理图”“NexArm-ESP32”“V1.0”，图中包含 ESP32 模组、总线舵机、I2C、USB-UART 等分区。
- 来源：`docs/NexArm机械臂/3.技术参数&图纸/1. NexArm主板原理图/SCH_NexArm V1.0.pdf`
- 来源位置：第 1 页标题栏和原理图分区
- 可信等级：B（厂商原理图）
- 适用范围：该 V1.0 图纸描述的控制器
- 最后核查时间：2026-07-29
- 备注：第 1 页已渲染核查；不证明当前实机就是 V1.0。

## F-005 STM32 资料覆盖多个 STM32F103C8T6 核心板变体

- 结论：硬件资料目录同时存在 `MICRO`、`TYPEC` 和“最小系统板”原理图，不能仅凭资料包名称判定当前实物板型。“最小系统板”图中可见 PA9/USART1_TX、PA10/USART1_RX、SWDIO、SWCLK、BOOT0 和 BOOT1 等网络。
- 来源：`docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板硬件资料/`
- 来源位置：三份原理图文件名；`STM32F103C8T6最小系统板原理图.pdf` 第 1 页
- 可信等级：B（核心板原理图资料）
- 适用范围：资料中的板型候选；不确认当前实物板型和接线
- 最后核查时间：2026-07-29
- 备注：第 1 页已渲染视觉核查。

## F-006 板端资料同时覆盖 Jetson Orin 官方套件、SUB 套件和 SUPER 相关流程

- 结论：`主板介绍.pdf` 明确并列 Jetson Orin 官方开发套件和 SUB 版开发套件；同一资料树另有 SUPER 系统/引导教程。因此资料集合本身不能唯一确定当前模块与载板。
- 来源：`docs/板端/02 第二章 主板基础/01.主板介绍/主板介绍.pdf`；`docs/板端/02 第二章 主板基础/06.烧写SUPER官方纯净系统（选看）/烧写SUPER官方纯净系统.pdf`
- 来源位置：`主板介绍.pdf` 第 1 页；SUPER 教程标题及第 1 页
- 可信等级：B（板端厂商教程）
- 适用范围：板端资料覆盖范围
- 最后核查时间：2026-07-29
- 备注：`主板介绍.pdf` 第 1 页已渲染；当前实机型号仍需确认。

## F-007 现有用户工程包含 K230/CanMV 视觉 UI 与 Arduino 机械臂代码

- 结论：`TaskSuite_E/` 中存在 Arduino/C++ 控制源码以及 `k230/game_vision.py`、`k230/suite_ui.py`；README 的运行说明要求 Arduino 烧录和 CanMV 运行 K230 脚本。
- 来源：`TaskSuite_E/README.md`；`TaskSuite_E/TaskSuite_E.ino`；`TaskSuite_E/k230/`
- 来源位置：README“烧录 / 运行”和“主要文件”
- 可信等级：D（用户自建工程及说明）
- 适用范围：现有 `TaskSuite_E` 工程结构
- 最后核查时间：2026-07-29
- 备注：只证明当前目录中的历史/现有实现，不能证明新 Jetson 路线应使用 K230 API。

## F-008 资料包保存了两个带版本名的 NexArm 固件文件

- 结论：固件目录存在 `NexArm_follower_V1.2_0x0000.bin` 和 `NexArm_leader_V1.1_0x0000.bin`。
- 来源：`docs/NexArm机械臂/2.软件&工具合集/8.出厂固件及烧录工具/01 NexArm出厂固件/NexArm_follower_V1.2_0x0000.bin`；`docs/NexArm机械臂/2.软件&工具合集/8.出厂固件及烧录工具/02 同步器出厂固件/NexArm_leader_V1.1_0x0000.bin`
- 来源位置：文件名和文件哈希见 `.cache/docs_index/file_manifest.json`
- 可信等级：A（实际固件文件存在）
- 适用范围：资料包内的固件候选
- 最后核查时间：2026-07-29
- 备注：不代表当前实机已烧录这些版本；缓存哈希仅用于定位和变更检测。
