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

## F-013 K230 TTL 请求式 JPEG（460800 / 1280×720）已在本机打通

- 结论：Jetson 经 CH343 USB-TTL（by-id `usb-1a86_USB_Single_Serial_5B7A028646-if00` → `ttyACM1`）与 K230 UART3（TX50/RX51）通信；协议 V2；固定 1280×720、JPEG q=65。烟雾 5/5、连续 100 次 100/100，平均约 2661 ms/帧，P95≈2746 ms，最大≈2828 ms，CRC/解码失败为 0。
- 来源：`2026E/drivers/k230_ttl_camera/`；Jetson `~/k230_ttl_camera` 烟雾与 `logs/stress_100.json` 输出；`docs/interfaces/k230_ttl_camera/`
- 来源位置：`protocol.py`；`jetson/k230_camera.py`；实机测试 JSON
- 可信等级：A（源码 + 实机）
- 适用范围：当前这套 CH343 序列号与已部署的 K230 `k230_camera_server.py`
- 最后核查时间：2026-07-30
- 备注：K230 原生 Kendryte CDC 仅用于 IDE/USBDBG，不作图传；K230 文件由人工写入 SD。

## F-014 Jetson Q1 实际根目录与 2026-07-30 无运动预检

- 结论：当前实机 `/proc/device-tree/model` 为 `NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super`，登录用户为 `jetson`。只读搜索确认原先不存在 `2026E`/`q1` 根目录，现将唯一 Q1 根目录定为 `/home/jetson/2026E`；原 `/home/jetson/k230_ttl_camera` 与桌面 NexArm 两套目录已移动到 `hardware/`，旧路径为兼容符号链接。
- 结论：固定 CH343 by-id 解析为 `/dev/ttyACM1`，K230 原生 CDC 为 `/dev/ttyACM0`。无运动预检的 READY/PING/STATUS/CAPTURE、CRC 与 1280×720 解码均通过，预热图保存到 `output/runs/20260730_012423_765015/captures/warmup.jpg`。
- 结论：本次枚举没有 `/dev/ttyUSB*` 或 NexArm by-id，故 NexArm 通信预检失败，未执行任何机械运动。
- 来源：Jetson `/proc/device-tree/model`、`/dev/serial/by-id/`、`lsusb`、`/home/jetson/2026E/output/runs/20260730_012423_765015/report.json`
- 来源位置：上述实机只读输出与报告 `checks` / `motion_executed`
- 可信等级：A（当前实机系统、设备枚举、源码和运行报告）
- 适用范围：2026-07-30 当前接线与已部署工程
- 最后核查时间：2026-07-30
- 备注：预热画面可见桌面散落线缆和右上方设备，不能据此确认机械臂运动空间已清空；相机支架与线缆走向仍须现场从机械臂外部检查。Jetson 系统时间比同为 `+08:00` 的控制端约慢 9 小时 20 分，当前 run ID/日志时间必须按该偏差理解。

## F-015 NexArm UART 端点与首次安装后低速 HOME 实测

- 结论：NexArm USB-UART 已枚举为 `/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0`（解析到 `/dev/ttyUSB0`），固件版本反馈为 `1.0.0`。首次 6000 ms 低速 HOME 命令从 `(23,2,121,-63,0,0)` 运动至反馈 `(195,4,200,-0.5,0,0)`，相对目标的三维合成位置残差为 6.40 mm，超过当时 5 mm 门限并在 12 s 后安全中止；后续无运动读取为 `(195,3,199,-0.7,0,0)`。
- 来源：Jetson `output/runs/20260730_013533_036667/report.*`、`output/runs/20260730_013618_569613/report.*`、`output/runs/20260730_013740_718035/report.*`
- 来源位置：各报告 `checks.nexarm_communication`、错误记录、位姿反馈
- 可信等级：A（当前实机运行报告）
- 适用范围：2026-07-30 当前 NexArm、安装负载、固件与接线
- 最后核查时间：2026-07-30
- 备注：反馈只能确认 SDK 报告的坐标，不能单独证明末端真实物理位置或绝对毫米精度；OBSERVE 与最终 HOME 尚未执行。

## F-016 A4 构图 HOME 首次低速实测未进入容差

- 结论：目标 `(150,0,230,-90,0,0)` 从初始反馈 `(2,0,147,-139.5,0,0)` 执行 6000 ms 低速动作后，12 s 超时时最终反馈为 `(160,4,222,-85.9,0,0)`；三维位置误差 13.42 mm，pitch 误差 4.1°，测试安全中止且未发送后续运动。用户根据现场方向判断将下一候选 pitch 调为 -93°。
- 来源：Jetson `output/runs/20260729_122043_166630/report.json`、`report.md`、`logs/arm_reset.log`
- 来源位置：报告 `checks.nexarm_communication`、`last_target_pose`、`error`
- 可信等级：A（当前实机运行报告）+ D（下一候选角度）
- 适用范围：当前 NexArm、相机安装负载、固件 1.0.0 与该次动作
- 最后核查时间：2026-07-30
- 备注：该运行只有运动前的 `warmup.jpg`，不能用于 HOME 构图判断；后续脚本已增加超时时的 `home_timeout.jpg` 取证。

## F-017 A4 构图 HOME 第二次低速实测仍未进入容差

- 结论：目标 `(150,0,230,-93,0,0)` 从初始反馈 `(160,4,222,-85.9,0,0)` 执行后，超时时最终反馈为 `(165,4,220,-86.6,0,0)`；三维位置误差 18.47 mm，pitch 误差 6.4°。超时图 `home_timeout.jpg` 显示 A4 上下边界仍未完整入画，但水平方向大致居中。用户随后将下一候选改为 `(150,0,300,-96,0,0)`，并明确保持位置容差 7 mm。
- 来源：Jetson `output/runs/20260729_123051_357485/report.*`、`captures/home_timeout.jpg`
- 来源位置：报告 `error`、`last_target_pose`、超时抓图
- 可信等级：A（当前实机运行报告与超时图）+ D（下一候选）
- 适用范围：当前 NexArm、相机安装负载、固件 1.0.0 与该次动作
- 最后核查时间：2026-07-30
- 备注：pitch 命令从 -90 到 -93 时实际反馈几乎不变，提示该姿态附近可能存在响应饱和；继续下调 pitch 需小步并保留取证。

## F-018 z=300/pitch=-96 候选不可达，改用实测停止位

- 结论：目标 `(150,0,300,-96,0,0)` 从 `(166,4,220,-85.5)` 附近发送后仅漂移到 `(173,4,226,-84.4)`，位置误差约 77.6 mm；用户描述为“响一下、几乎不移动”。结合厂商示例中高 z 与向下 pitch 通常不同时使用，判定该组合当前不可达。用户随后旋转 A4 90°，并批准将 HOME 改为该实测停止位，同时要求软件安全范围与 HOME 分离并保留余量。
- 来源：Jetson `output/runs/20260729_124259_493009/report.*`、`captures/home_timeout.jpg`；`docs/.../UART_Control/basic_demo.py`
- 来源位置：报告 `poses[0]` / `error`；示例 `PICK_PLACE_SEQUENCE`
- 可信等级：A（实机报告）+ C（厂商示例用法）+ D（下一 HOME 候选）
- 适用范围：当前安装负载与固件 1.0.0
- 最后核查时间：2026-07-30
- 备注：软件 `workspace_limits` 扩展不是拦截原因；`set_pose` 无应答，固件是否拒绝或限幅无法从 SDK 直接确认。

## F-019 实测停止位可重复到达且旋转后 A4 完整入画

- 结论：目标 `(173,4,226,-84.4,0,0)` 从 `(37,0,145,-132.4,0,0)` 低速到达实际 `(174,2,227,-83.7,0,0)`，三维位置误差 2.45 mm、pitch 误差 0.7°，运行成功完成。旋转 90° 后的 A4 四边完整入画；边框下边约比上边宽 10%，提示 Pitch 方向仍有透视倾斜。
- 来源：Jetson `output/runs/20260729_125749_401725/report.*`、`captures/home.jpg`
- 来源位置：报告 `poses[0]`、`images.home`；图片边框直线测量
- 可信等级：A（实机报告与图片）+ D（透视原因工程分析）
- 适用范围：当前相机支架、桌面、A4 旋转方向与固件 1.0.0
- 最后核查时间：2026-07-30
- 备注：A4 完整入画不等于无透视；正式几何测量仍须用该固定姿态重新做 A4 四角透视标定。
