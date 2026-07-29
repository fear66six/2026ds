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

## F-009 当前 STM32 可通过 COM15 的 USART1 系统 Bootloader 只读访问

- 结论：ATK-MO340P 对应 Windows 设备 `USB-Enhanced-SERIAL CH343 (COM15)`，VID/PID 为 `1A86:55D3`。STM32CubeProgrammer 2.23.0 以 115200、8E1、无流控成功连接，返回 Chip ID `0x410`、Bootloader protocol `2.2`；Flash-size 系统寄存器 `0x1FFFF7E0` 返回 `0x0040`（64 KiB），RDP 为 `0xA5` Level 0。已从 `0x08000000` 读取 65,536 字节完整备份。
- 来源：`logs/stm32_uart_bootloader/connection_115200.log`；`logs/stm32_uart_bootloader/flash_size_register.log`；`logs/stm32_uart_bootloader/option_bytes_display.log`；`backup/stm32_before_uart_magnet/backup_manifest.json`
- 来源位置：CubeProgrammer 连接输出、系统寄存器读取结果、Option Bytes 只读显示和备份清单
- 可信等级：A（当前设备只读查询与实际备份产物）
- 适用范围：2026-07-29 本次通过 COM15 连接的当前 STM32；COM 号以后可能变化
- 最后核查时间：2026-07-29
- 备注：CubeProgrammer 的系列默认显示为 128 KiB 并带容量警告，实际容量以芯片 Flash-size 寄存器的 64 KiB 为准；UART Bootloader 未返回 Revision ID。F-009 所述只读检查阶段未执行擦除、写入、启动或 Option Bytes 修改；后续经明确授权的写入另见 F-010。

## F-010 USART1 电磁铁控制固件已通过 UART Bootloader 写入并复核

- 结论：用户给出明确烧录授权后，CubeProgrammer 2.23.0 通过 COM15 将 `firmware.hex` 写入 `0x08000000`，仅擦除内部页 0 至 3，并返回 `Download verified successfully`。随后独立回读 3,648 字节，SHA256 与构建 BIN 相同。
- 来源：`logs/stm32_uart_bootloader/program_and_verify.log`；`logs/stm32_uart_bootloader/post_flash_readback.log`；`FLASHING_REPORT.md`
- 来源位置：下载日志的擦除范围、Verify 结果和回读日志；回读 SHA256 为 `705FD75A48CC55A15B7E25AA352D7E1C2F98CFF57FA66C3717D600D36B33B868`
- 可信等级：A（当前设备实际烧录、Verify 和独立回读）
- 适用范围：2026-07-29 当前通过 COM15 连接的 STM32
- 最后核查时间：2026-07-29
- 备注：烧录命令阶段未执行 Go/Start、烧录后复位、Option Bytes 或 RDP 修改；之后用户已手动恢复 BOOT0 并复位，应用层测试结果见 F-011。

## F-011 烧录后 USART1 应用通信与默认关闭状态已通过实机验证

- 结论：用户将 BOOT0 恢复为 0 并复位后，通过 ATK-MO340P 的 COM15 以 115200、8N1、无流控通信。`MAGNET_OFF` 返回 `OK OFF`，连续 10 次 `PING` 均返回 `PONG`，`GET_STATUS` 返回 `STATUS MAGNET=0 FAULT=0`。
- 来源：`logs/stm32_uart_bootloader/usart1_runtime_test.log`；`USART1_TEST_REPORT.md`
- 来源位置：完整收发日志
- 可信等级：A（当前设备实机串口测试）
- 适用范围：2026-07-29 当前烧录固件和 ATK-MO340P COM15 链路
- 最后核查时间：2026-07-29
- 备注：测试未发送 `MAGNET_ON`；MOSFET、电磁铁和负载电源仍未连接。板载 Micro-USB 因固件不实现 USB 设备栈而出现 Windows Code 43，不影响独立的 COM15 USART1 链路。

## F-012 Q1 图 2 目标矩形为 10 cm × 6 cm 四片拼合

- 结论：赛题 PDF 第 2 页图 2 要求四片自备碎片拼成 10 cm × 6 cm 矩形；`2026E/q1/pieces.py` 以左上角为原点、x 向右、y 向下定义外框与对角线分点，四片面积和为 60 cm²。目标区默认放在 A4 下半区水平居中、距分界线 2 cm，左上角纸面坐标 `(55.0, 168.5) mm`。
- 来源：`docs/E题_拼图装置.pdf` 第 2 页；`2026E/q1/pieces.py`；`2026E/q1/config.py` 的 `TARGET_ORIGIN_*`
- 来源位置：图 2 尺寸标注；`verify_geometry_invariants()`；`TARGET_ORIGIN_X_CM` / `TARGET_ORIGIN_Y_CM`
- 可信等级：B（赛题 PDF）+ A（源码几何校验）
- 适用范围：Q1 视觉匹配、单步规划与完成判定
- 最后核查时间：2026-07-29
- 备注：纸面内旋转在规划中映射到 NexArm `set_pose` 的 `roll` 字段；零位/方向/范围须由 `arm_calibration` JSON 实机标定，不得伪造默认值。
