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

## F-020 pitch=-90 HOME 复测未运动，恢复已验证的 -84.4

- 结论：Z150 标定下降测试发送 HOME `(173,4,226,-90,0,0)` 后，反馈从开始到 12 s 超时始终为 `(183,3,220,-85.7,0,0)`；位置误差 11.70 mm、pitch 误差 4.3°，程序按门禁未发送后续 Z=150 指令。该结果不能证明固件是拒绝、限幅或逆解失败，但足以否决把 -90 作为已验证 HOME；项目恢复运行 `20260729_125749_401725` 完整到位过的 `pitch=-84.4`。
- 来源：Jetson `python3 -m q1.scripts.test_arm_z150_calibration --confirm RUN_ARM_Z150` 控制台输出；`q1/scripts/test_arm_z150_calibration.py`
- 来源位置：`INITIAL_CURRENT_POSE`、HOME `TimeoutError`、`FINAL_CURRENT_POSE`
- 可信等级：A（实机反馈）+ D（恢复 HOME 的工程决策）
- 适用范围：当前相机支架、NexArm 固件 1.0.0 与当前装配
- 最后核查时间：2026-07-30
- 备注：不能通过放宽到位容差继续下降；梯形透视改由纸面透视标定或相机支架处理。

## F-021 HOME Z241 实测未到位

- 结论：正式 Q1 发送 HOME `(173,4,241,-84.4,0,0)` 后最终反馈 `(168,5,219,-86.9,0,0)`，三维位置误差 22.58 mm，超过 10 mm 门限；控制器在拍照和抓放前停止，未发送恢复位姿。该结果否决了把 Z241 和随之提高的 Z265 安全高度作为当前正式候选。
- 来源：Jetson 运行 `20260729_132716_886467` 控制台 traceback、`output/runs/q1/20260729_132716_886467/failure.json`
- 来源位置：`q1/controller.py::Q1Controller.run` HOME 到位门限；异常中的 target、actual 与 error
- 可信等级：A（实机反馈）+ D（回退工程决策）
- 适用范围：当前 NexArm、相机支架、固件与 `(x=173,y=4,pitch=-84.4)` 组合
- 最后核查时间：2026-07-30
- 备注：现有证据不能区分逆解不可达、固件拒绝或机械限幅；不得通过放宽容差继续。

## F-022 独立 Z25 运动时坐标与舵机反馈保持陈旧

- 结论：从 HOME 容差内反馈 `(168,5,219,-86.9,0,0)` 向 `(246,35,25,-84.4,0,0)` 发送一次 6000 ms 完整位姿命令。用户现场确认机械臂发生了物理运动，但约 12 秒内记录的 79 个坐标样本和六路舵机位置均保持在命令前数值。程序因反馈未到目标而超时，未发送 HOME 或任何后续位姿。该运行是保留的唯一 `q1_pose_calibration` 原始证据目录。
- 来源：Jetson `output/runs/q1_pose_calibration/20260729_153642_988359/report.json`；当前 `hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py`（含 `flush_input_buffer` / 请求时间戳诊断）；`q1/executors/nexarm.py`
- 来源位置：报告 `feedback_samples`、`last_servo_positions`、`max_observed_motion_mm`、`arrival_result` 和 `error`
- 可信等级：A（当前实机反馈与项目源码）+ D（用户现场运动观察）
- 适用范围：当前 NexArm、固件 1.0.0、安装负载及该完整 XYZ/Pitch/Roll/Claw 组合
- 最后核查时间：2026-07-30
- 备注：该结果证明当时 `get_current_coords()`/舵机反馈不能可靠反映这次物理运动，不能再把“反馈未变化”表述为“机械臂未运动”。现场观察也尚不能单独证明精确到达 Z25。独立单目标标定脚本已删除；正式路径以 flush 后请求时间戳判定新鲜度，大行程无反馈变化视为 `STALE_FEEDBACK_HARDWARE_FAULT`。

## F-023 当前负载下名义 HOME (173,4,226,-84.4) 稳定停在 Z≈214 / pitch≈-88

- 结论：受控 Q1 运行 `20260729_162553_094642` 从 `(233,34,23,-85.6)` 发送 HOME `(173,4,226,-84.4,0,0,6000)` 后，反馈变化约 203 mm，约 6.8 s 起稳定在 `(169,7,214,-88.5)`，位置误差 13 mm、姿态误差 4.1°，判定 `TIMEOUT_AFTER_FEEDBACK_CHANGE`；未进入视觉、源位姿或磁铁。随后无磁铁 HOME-only `20260729_163015_521142` 从近邻 `(169,5,215,-88.1)` 再发同一命令，最大反馈变化仅 1.414 mm，终点 `(168,5,214,-88.6)`，同样超时。控制板断电重启后，运行 `20260729_164647_578613` 明确不发送 `CMD_SET_GLOBAL_ACC`，起点 `(168,5,215,-88.0,1,1)`，同一 HOME 命令后坐标与六路舵机变化均为零，判定 `STALE_FEEDBACK_HARDWARE_FAULT`。
- 软件审计结论：部署 SDK 与厂商 UART `set_pose`/`get_current_coords`/`set_global_acceleration` 的命令号、字段顺序、缩放与字节序一致；主机不会在 duration 内发送中途停止。本次失败不是编码错误，也不是新鲜度误判。
- 来源：Jetson `output/runs/q1/20260729_162553_094642/failure.json`；`output/runs/20260729_163015_521142/report.json`；`output/runs/20260729_164647_578613/report.json`；`docs/_nexarm_extract/UART_Control/nexarm_sdk.py`；`2026E/hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py`
- 可信等级：A（实机报告与源码比对）
- 适用范围：当前固件 1.0.0、挂载相机/磁铁负载；已覆盖设置 `global_acceleration=10` 与断电后保留控制板默认加速度两种情况
- 最后核查时间：2026-07-30
- 备注：历史可达盆约为 `(174,2,227,-83.7)` 与后来的 `(168,5,219,-86.7)`。当前停点更低/更俯。断电重启且不发送全局加速度后仍失败，已排除 `global_acceleration=10` 是单一根因；只读检查随后排除了当前动作编辑/回放、位置偏差、运动学参数、HOME IK 和坐标限位异常。`set_pose` 无应答，主机无法确认固件是否执行目标。旧 HOME 后由 D-029 作为项目决策覆盖。

## F-024 当前稳定反馈停点为 (168,5,215,-88,1,1)

- 结论：断电后保留控制器加速度的 HOME 复测、后续只读真实 TCP 查询和再次受控 HOME 复测均稳定报告约 `(168,5,215,-88,1,1)`，六路舵机约为 `[2030,2099,2032,3085,2056,2056]`。对旧 HOME 的纯 IK 查询可生成不同目标脉冲，说明稳定停点不是主机把旧目标原样回显。
- 来源：Jetson 运行 `20260729_164647_578613`、`20260729_170513_284352`；`output/diagnostics/nexarm_readonly/20260729_170214.json`
- 来源位置：运行报告 `last_actual`、反馈样本与只读报告的 `current_coords_samples`、`real_joint_angles`、`real_tcp_pose_samples`、`ik_calc_only`
- 可信等级：A（实机反馈和只读协议回包）
- 适用范围：当前 NexArm、固件 ESP32 1.0.0 / AT32 1.0.2、当前挂载负载
- 最后核查时间：2026-07-30
- 备注：D-029 当时将项目 HOME 定义为 `(168,0,230,-88,1,1)`；该定义是用户决策，不等同于执行链路故障修复。相对此稳定停点约 ΔY=5 mm、ΔZ=15 mm，若反馈不变则会超过现有 10 mm 到位容差。当前 HOME 后续已由 D-034 改为 `(180,0,200,-90,0,0)`。

## F-025 HOME 前出现下探的最新现场现象

- 结论：用户于 2026-07-30 报告当前复位流程从开机位置先向下移动至地面，再回到 HOME。修改前的两个真实入口都在 HOME `set_pose` 前发送 `CMD_SET_GLOBAL_ACC`，但主机源码中不存在向下中间位姿。
- 来源：用户现场观察（D）；`2026E/q1/scripts/test_camera_arm_reset.py`、`q1/executors/nexarm.py::initialize`、厂商出厂程序 `system_task_handle.cpp::CMD_SET_GLOBAL_ACC`（A）。
- 固件事实：出厂处理函数对 `CMD_SET_GLOBAL_ACC` 保存参数，广播舵机加速度寄存器并向下级发送 `CMD_SET_MOVE_ACC`；对 `CMD_COORDINATE_SET` 则直接转发完整目标。源码不能证明实机下探由哪一条命令触发。
- 工程处理：D-035 删除 Q1 的全局加速度写入，使 HOME 成为握手读取后的第一条控制器写命令。
- 待实机验证：重新接线并上传后运行一次 HOME；若仍下探，需把现象归入单条 HOME 的控制板/舵机内部轨迹，而不是 Python 中间位姿。

## F-026 HOME (180,0,200,-90,0,0) 零运动复测

- 结论：运行 `20260730_231532_316942` 从反馈位姿 `(500,0,73,0,0,0)` 发送 HOME `(180,0,200,-90,0,0)` 后，坐标和六路舵机反馈在整个等待期内均无变化，判定 `STALE_FEEDBACK_HARDWARE_FAULT`；后续 `plan` 命令因 `&&` 未执行。
- 来源：用户下载的运行目录 `D:\OIK\Downloads\20260730_231532_316942\report.md`（实机运行报告）。
- 来源位置：预检 `nexarm_communication`、位姿记录 `home_timeout`、`feedback_samples`。
- 可信等级：A（当前实机协议回包）；是否需要实机验证：是，新 HOME 仍未验证。
- 工程边界：D-036 将后续观察位改为 `(175,0,210,-90,0,0)` 以改善纸张取景，但位姿值变化本身不能修复该零运动执行故障。

## F-027 HOME 超时图可完成当前 Q1 识别与四片规划

- 结论：运行 `20260730_232815_277491` 的复位脚本在 HOME 后因陈旧反馈非零退出；Shell 使用 `&&`，因此后续 `q1.main plan` 没有启动，这就是该次“没有识别”的直接原因。该运行的 `home_timeout.jpg` 经当前 `SceneAnalyzer`、`plan_piece_moves` 离线复算后得到 `paper_valid=true`、`scene_valid=true`、4 块碎片和 `P1,P2,P3,P4` 四条规划，并生成 `capture.png`、`plan.png`、`scene.json`、`piece_moves.json`。
- 来源：`D:\OIK\Downloads\20260730_232815_277491\report.json`、`captures/home_timeout.jpg`；`2026E/q1/workflow.py::capture_and_plan`、`SceneAnalyzer`、`plan_piece_moves`。
- 可信等级：A（实机原始图、运行报告和当前源码离线执行）；是否需要实机验证：视觉识别结论不需要，修改后的完整 `run` 仍需要实机执行。
- 适用范围：当前 A4 摆放、四块实物、K230 取景和本次源码版本。
- 最后核查时间：2026-07-30。

## F-028 当前自备四片检测尺寸比图 2 名义模板大约 3%

- 结论：成功完整运行 `20260731_012300_357937` 的四片源多边形面积分别约为 `499.75、1021.62、2216.76、2637.05 mm²`，合计 `6375.18 mm²`；赛题图 2 的 10×6 cm 矩形名义面积为 `6000 mm²`。统一线性比例为 `sqrt(6375.18/6000)=1.0308`。以 `1.03` 缩放目标后，外包框为 `103×61.8 mm`，同一实图四片刚体拟合最大误差为 `0.751、1.633、0.936、1.977 mm`，均低于 8 mm 门限。
- 来源：`docs/E题_拼图装置.pdf` 第 2 页图 2；`D:\OIK\Downloads\20260731_012300_357937\capture.png`、`scene.json`、`piece_moves.json`；当前 `q1/analyzer.py`、`q1/pieces.py` 离线复算。
- 可信等级：B（赛题尺寸）+ A（实机图、JSON 和源码复算）；是否需要实机验证：需要，缩放后的释放位置尚未部署执行。
- 工程边界：不能从单次视觉测量区分实物制作尺寸偏差与轮廓测量系统误差；比例只适用于当前固定四片，不适用于现场未知碎片。
- 最后核查时间：2026-07-31。

## F-028 STM32F103VET6 电磁铁固件已移植并通过串口与 100ms 吸合测试

- 结论：新工程位于 `firmware/stm32f103ve_uart_magnet`，目标 MCU 为 STM32F103VE（高密度，`STM32F10X_HD`），启动文件 `startup_stm32f10x_hd.s`，Flash `0x08000000+512KiB`，SRAM `0x20000000+64KiB`。应用协议仍为 USART1 115200 8N1 的 `PING`/`GET_STATUS`/`MAGNET_ON`/`MAGNET_OFF`/`EMERGENCY_OFF`。Windows 侧 CubeProgrammer 识别芯片 ID `0x414`（STM32F101/F103 High-density，512KB），阶段 A `stm32f103ve_uart_ping.hex` 烧录 Verify 成功且 PING 20/20；阶段 B `stm32f103ve_uart_magnet.hex`（控制脚 PC0）烧录 Verify 成功。Jetson 路径 `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00` 上 `PING=True`、`STATUS MAGNET=0 FAULT=0`，`MAGNET_ON 100` 应答成功，250ms 后状态为关，并完成 `MAGNET_OFF`/`EMERGENCY_OFF`。
- 来源：`firmware/stm32f103ve_uart_magnet/inc/board_config.h`、`src/main.c`、`src/magnet_control.c`、`build/BUILD_REPORT.md`、`build/stm32f103ve_uart_magnet.hex`（A）；CubeProgrammer 探测/烧录输出与 Windows/Jetson 串口测试输出（A）；用户确认 PC0 引出与占用情况（D）。
- 可信等级：A（源码、烧录与串口测试）+ D（板卡 PC0 映射确认）
- 适用范围：当前 VET6 板、ATK 序列号 `5B7A030191`、PC0→MOSFET 控制端接线；不覆盖旧 C8T6/`PB12` 工程
- 最后核查时间：2026-07-31
- 备注：旧工程 `firmware/stm32f103_uart_magnet` 保持未覆盖。`STATUS MAGNET=0` 仍只证明固件锁存关闭，不能单独证明线圈无电流；吸合磁力与工件吸取仍待视觉/现场验证。
