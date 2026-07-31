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

## F-035 三次运行的 P4 原吸取中心贴近拟合边界

- 结论：运行 `20260730_232827_207582`、`20260730_233201_481210`、`20260730_233351_970591` 中，P4 旧 `center_mm` 到拟合三角形边界的距离分别约为 `1.19 mm`、`0.45 mm`、`2.12 mm`。改用最大内接点后分别约为 `20.35 mm`、`19.77 mm`、`20.48 mm`。
- 离线复算：三次图像均保持 `paper_valid=true`、`scene_valid=true` 和四片规划成功；P1-P4 的边界余量均增加。所有低位 clearance 相邻段同时改变 X/Y/Z，吸合后的首个目标使用完整 release roll。
- 来源：三份运行目录中的 `capture.png`、`scene.json`、`piece_moves.json`、`moves/*.json`；`2026E/q1/geometry.py::polygon_maximum_clearance_point`、`motion.py::plan_single_move`、`executors/nexarm.py::execute_single_move`；当前源码离线执行。
- 可信等级：A（图像、JSON、源码和离线复算）+ D（`X/Y +5 mm` 与触地现场观察）；是否需要实机验证：需要，新的吸取位置、clearance 轨迹和 roll 时序尚未在 NexArm 上执行。
- 最后核查时间：2026-07-31。

## F-032 成功全流程的低位直达搬运存在现场下沉现象

- 结论：运行 `20260730_215916_405845` 成功完成一次识别、四片规划和全部命令时长；四片吸取与释放命令的 Z 均为 `-15`，旧执行器在磁铁吸合后只发送一条从吸取点到释放点的 6000 ms 位姿。日志没有运动中连续的新鲜坐标，不能从记录证明实际 Z 曲线；用户现场观察到到达 `-15` 后搬运前半段继续降低。
- 工程处理：搬运改为固定缓冲位姿 `[175,0,80,-90,0,0,3000]`。第一片从 HOME 直接到吸取点，吸合后经 BUFFER 到释放点；后续每片从上一释放点先回 BUFFER，再到吸取点，吸合后再次经 BUFFER 到释放点；最后一片释放后返回 HOME。
- 来源：`20260730_215916_405845/final.json`、`piece_moves.json`、`moves/*.json`；用户现场观察；`2026E/q1/motion.py`、`executors/nexarm.py`；厂商 `编程定点夹取搬运/Nex_Arm.zip!/system_task_handle.cpp::kPickPlaceSequence`。
- 可信等级：A（历史运行目标和当前源码）+ C（厂商固定中间位姿示例）+ D（现场观察与 BUFFER 参数决策）；是否需要实机验证：需要。
- 离线核对：固定 BUFFER 与运行 `20260730_215916_405845` 的四组吸取/释放端点之间均同时改变多个坐标轴；当前源码不生成单轴增量航段。
- 最后核查时间：2026-07-31。

## F-033 NexArm 静止末端抖动期间上位机目标与关节回读未变化

- 结论：只读诊断 `20260730_233809_392899` 未发送运动或电磁铁命令；控制板电压为 `12419`（约 12.419 V）。约 2 秒内以 100 ms 间隔读取 20 次 `CMD_GET_REAL_JOINT_ANGLES`，六轴脉冲均保持 `[2233,1536,1780,2302,2048,2048]`，各轴回读跨度均为 0。用户同时观察到末端机械抖动。
- 限制：项目此前已确认 NexArm 坐标/舵机反馈可能滞留，因此跨度为 0 只能排除“上位机观察到的目标或回读变化”，不能证明舵机内部位置环、供电瞬态或机械结构没有振动。舵机模式、扭矩、目标/当前位置、电压、温度和电流寄存器直读仍全部超时。
- 现场状态冲突：诊断回读 TCP 为 `(227,-66,-22,-90.8,0,0)`，不是配置 HOME `(175,0,210,-90,0,0)` 或 BUFFER `(175,0,80,-90,0,0)`。由于反馈可能滞留，不能据此确认实物当时真实位置；若末端实际接触桌面或工件，接触负载是待排查因素。
- 来源：用户提供的 `/home/jetson/2026E/output/diagnostics/nexarm_readonly/20260730_233809_392899.json` 输出；`2026E/q1/scripts/diag_nexarm_controller_state.py::sample_real_joints`；幻尔 HX 系列舵机手册供电与堵转说明。
- 可信等级：A（诊断命令、协议回包和软件采样）+ B（厂商供电/堵转说明）+ D（用户现场抖动观察）；是否需要实机验证：需要。
- 最后核查时间：2026-07-31。

## F-031 正式 Q1 启动下探发生在 HOME 前且主机未发送下探位姿

- 结论：运行 `20260730_211654_514549` 的事件顺序为相机初始化、NexArm 初始化、STM32 初始化、HOME；NexArm 串口打开后的首次坐标反馈已经是 `(227,-66,-22,-90.8,0,0)`，主机记录的唯一运动目标为 HOME `(175,0,210,-90,0,0)`，时长 6000 ms。用户现场观察到启动后机械臂先快速触地再回 HOME，但现有日志和 Python 源码中不存在向下中间位姿命令。
- 工程处理：正式入口先打开 NexArm，串口 `open()` 返回后立即把 HOME 作为第一条协议命令发送，再查询同一目标的 IK 脉冲并等待实际六轴脉冲到位；HOME 完成后不再追加固件/坐标查询，直接初始化相机与 STM32。HOME 独立时长为 3000 ms，抓放仍为 6000 ms，但时长均不再作为流程推进依据。
- 来源：用户现场观察；`20260730_211654_514549/events.jsonl`、`failure.json`；`2026E/q1/controller.py`、`executors/nexarm.py`、`hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py::open/set_pose`。
- 可信等级：A（运行日志与源码）+ D（现场物理观察和工程时长决策）；是否需要实机验证：需要，尚未同步 Jetson。
- 适用边界：该修改消除主机在串口打开后发送 HOME 前的查询、设备初始化和日志等待；若更新后仍先下探，则剩余原因在串口打开触发、控制板旧目标恢复或舵机内部行为，不能归因于 Python 发送了第二个位姿。
- 最后核查时间：2026-07-31。

## F-030 Q1 纸面到机械臂 XY 已按当前横放 A4 四角重新标定

- 结论：用户在 1280×720 当前构图中测得图像 TL/TR/BL/BR 像素约为 `(136,16)`、`(1112,10)`、`(133,703)`、`(1114,707)`，对应机械臂 XY 为 `(328,139)`、`(331,-130)`、`(139,138)`、`(132,-134)`。横放图像四角在程序标准纸面坐标中依次对应 `(0,0)`、`(0,297)`、`(210,0)`、`(210,297) mm`。
- 实现：`q1/config/robot_config.json::paper_to_robot_matrix` 更新为四点仿射最小二乘矩阵；四点二维 RMS 残差约 `2.61 mm`，纸面中心 `(105,148.5) mm` 映射到机械臂约 `(232.5,3.25) mm`。
- 图像复算：`0cfcb4c024981bd1d47b4a83a06af8a8.png` 自动检测纸框为 `(133,8)..(1121,709)`，得到 `paper_valid=true`、`scene_valid=true`、P1–P4 齐全，并成功生成四条带机械臂 XY/Z 的规划。
- 来源：用户 2026-07-31 四角像素与机械臂实测；`2026E/q1/vision.py`、`calibration.py::ArmCoordinateMapper`、`config/robot_config.json`；当前源码离线执行。
- 可信等级：A（源码、配置和离线执行）+ D（用户实测输入及仿射拟合决策）；是否需要实机验证：需要，标定更新后尚未执行真实抓放。
- 最后核查时间：2026-07-31。

## F-029 当前横放构图可由左右黑色半区和白色中线恢复裁切 A4

- 结论：旧固定灰度阈值会因左右半区受光不均而稳定选择较深的右半区。当前主流程改用 Otsu 相对阈值寻找宽度接近、水平相邻的左右黑色半区，并要求两者之间存在窄而连续的亮色分界线。若上边或下边超出画面，则由完整可见的 29.7 cm 长边和 A4 固定比例向画外恢复 21 cm 短边，避免把可见高度错误缩放为完整纸高。
- 来源：用户提供的 `2026E/output/plans/q1/sim_clipped_a4_20260731/img1..img3/capture.png`；`2026E/q1/vision.py::detect_paper`、`_find_paper_frame_from_split_halves`；当前源码离线执行。
- 可信等级：A（源码与三张样本离线执行）+ B（A4 固定尺寸）+ D（当前固定横放构图）；是否需要实机验证：需要，尚未同步 Jetson。
- 离线结果：三张 1024×767/768 特殊构图均为 `paper_valid=true`、`scene_valid=true`，P1–P4 齐全且均属于左侧 `UPPER_SOURCE`；恢复出的纸框分别为 `(34,123)..(1010,813)`、`(59,93)..(1023,775)`、`(39,-19)..(1001,661)`。
- 新增复核：运行 `20260730_211654_514549` 的 1280×720 原图中，左右暗区为 `x=140..638` 和 `x=644..1149`，阈值分割后的有效亮缝仅 5 px。旧的 0.4% 图宽下限为 5.12 px，导致成对候选仅差 0.12 px 被拒绝并回退到右半框；下限改为 `max(2 px, 0.2% 图宽)` 后恢复纸框 `(140,0)..(1149,713)`，四片识别和规划均通过。
- 适用边界：A4 必须横放，左右黑色半区、中央白线和四片必须可见；不覆盖碎片本身被裁切、左右纸边缺失或构图大幅偏移。
- 最后核查时间：2026-07-31。

## F-028 STM32F103VET6 电磁铁固件已移植并通过串口与 100ms 吸合测试

- 结论：新工程位于 `firmware/stm32f103ve_uart_magnet`，目标 MCU 为 STM32F103VE（高密度，`STM32F10X_HD`），启动文件 `startup_stm32f10x_hd.s`，Flash `0x08000000+512KiB`，SRAM `0x20000000+64KiB`。应用协议仍为 USART1 115200 8N1 的 `PING`/`GET_STATUS`/`MAGNET_ON`/`MAGNET_OFF`/`EMERGENCY_OFF`。Windows 侧 CubeProgrammer 识别芯片 ID `0x414`（STM32F101/F103 High-density，512KB），阶段 A `stm32f103ve_uart_ping.hex` 烧录 Verify 成功且 PING 20/20；阶段 B `stm32f103ve_uart_magnet.hex`（控制脚 PC0）烧录 Verify 成功。Jetson 路径 `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00` 上 `PING=True`、`STATUS MAGNET=0 FAULT=0`，`MAGNET_ON 100` 应答成功，250ms 后状态为关，并完成 `MAGNET_OFF`/`EMERGENCY_OFF`。
- 来源：`firmware/stm32f103ve_uart_magnet/inc/board_config.h`、`src/main.c`、`src/magnet_control.c`、`build/BUILD_REPORT.md`、`build/stm32f103ve_uart_magnet.hex`（A）；CubeProgrammer 探测/烧录输出与 Windows/Jetson 串口测试输出（A）；用户确认 PC0 引出与占用情况（D）。
- 可信等级：A（源码、烧录与串口测试）+ D（板卡 PC0 映射确认）
- 适用范围：当前 VET6 板、ATK 序列号 `5B7A030191`、PC0→MOSFET 控制端接线；不覆盖旧 C8T6/`PB12` 工程
- 最后核查时间：2026-07-31
- 备注：旧工程 `firmware/stm32f103_uart_magnet` 保持未覆盖。`STATUS MAGNET=0` 仍只证明固件锁存关闭，不能单独证明线圈无电流；吸合磁力与工件吸取仍待视觉/现场验证。

## F-034 正式 Q1 的 HOME 实体到位但笛卡尔反馈保持开机值

- 结论：运行 `20260730_220506_814308` 和 `20260730_220532_003590` 均向 HOME `(175,0,210,-90,0,0)` 成功发送命令；用户现场观察机械臂已移动到 HOME，但程序连续约 12 秒只收到 `(500,0,73,0,0,0)`，旧逻辑因此在相机初始化前退出。两份目录均没有照片、规划或抓放动作。
- 来源：`D:\OIK\Downloads\20260730_220506_814308\failure.json`、`events.jsonl`；`D:\OIK\Downloads\20260730_220532_003590\failure.json`、`events.jsonl`（A）；用户现场到位观察（D）。
- 工程处理：D-043 不再用笛卡尔反馈或总时长超时终止生产运动，改为 IK 目标脉冲与实际六轴脉冲的目标误差和静止条件；HOME 到位后直接进入唯一一次正式拍照、识别和规划。
- 后续实测：运行 `20260730_224434_329023` 仍从 `CMD_GET_CUR_COORDS` 读取附带脉冲，程序停在 `MOVE_TO_OBSERVE`；约 25 秒后用户以 `Ctrl+C` 中断，`failure.json` 为 `KeyboardInterrupt`，未进入 `INITIALIZE_CAMERA`，因此不是拍照卡住。生产闭环随后改用此前只读报告已成功返回的 `CMD_GET_REAL_JOINT_ANGLES`。
- 再次实测：运行 `20260730_230752_091605` 改用真实关节读取后仍停在 `MOVE_TO_OBSERVE`，约 39 秒后由用户中断；报告只有 IK 目标脉冲 `[2048,2068,2045,3089,2048,2048]`，没有任何实际关节样本，也未进入相机初始化。D-044 因此恢复成功版本的动作时长推进，并统一增加 1 秒机械稳定等待。
- 可信等级：A（命令、回包和失败阶段）+ D（实体 HOME 到位）；是否需要实机验证：需要，目标关节闭环尚未同步 Jetson 执行。
- 最后核查时间：2026-07-31。

## F-036 pintu 的 release roll 包含基座摆臂方位角补偿

- 来源确认事实：`D:\OIK\Downloads\pintu\jetson_to_nexarm\puzzle_runner.py` 第 31–57 行以吸取/释放机器人 XY 的 `atan2` 方位差计算较小夹角，并乘配置符号；第 165–174 行把补偿叠加到几何 place roll 后归一化；第 245–268 行在空中旋转和转运阶段使用该最终角。`algorithm/bridge/run_execute.py` 第 405–415 行默认启用并取 `swing_roll_sign=-1.0`。
- Q1 实现事实：`q1/motion.py::plan_single_move` 在吸取端 `+5/+5 mm` 修正后，用最终命令 XY 计算摆角；`release_roll_deg` 表示归一化后的最终命令，规划 JSON 另存 `geometric_release_roll_deg`、`swing_azimuth_deg` 和 `swing_roll_compensation_deg`。`q1/executors/nexarm.py::execute_single_move` 先以 pick roll 抬到 `Z=120`，再在吸点上空独立转到最终 release roll，并在同高转运和释放阶段保持该角度。
- 离线复算：运行 `20260730_232827_207582`、`20260730_233201_481210`、`20260730_233351_970591` 均保持 `paper_valid=true`、`scene_valid=true` 和 P1–P4 四片规划成功；12 个摆角为 `25.156°..52.757°`。
- 可信等级：A（pintu/Q1 源码和三组实图离线执行）+ D（采用 `-1.0` 作为当前实机方向决策）；是否需要实机验证：需要，公式已确认但物理修正符号和释放角精度尚未由真实拼放结果确认。
- 最后核查时间：2026-07-31。

## F-037 队友 pintu 与当前 Q1 的可复用差异已完成源码对照

- 相同部分：`pintu/algorithm/q1` 与当前 Q1 的 `vision.py`、`white_segmentation.py`、`edge_refinement.py` SHA256 分别相同，因此没有证据支持替换当前视觉主链路。当前 Q1 另外保留最大内接吸取点和已完成的残缺 A4 适配。
- 可复用部分：`pintu/algorithm/q1/puzzle_solver.py` 按 `target_scale` 构造模板特征；`pieces.py::apply_edge_gap_mm` 将每片向目标中心外移动 `gap/2`；`motion.py` 使用 `P4,P3,P2,P1` 大到小顺序；`puzzle_runner.py::_rotate_duration_ms` 按 roll 角度比例分配旋转时间。
- 执行层复用边界：用户后续以队友实机效果为依据，明确要求采用 `puzzle_runner.py::execute_one` 的分段 transfer，因此当前 Q1 已复用纯 Z 抬升、`Z=120` 同高转运和吸点上空独立 roll；仍不采用可选相对 X peel，也不采用 `arm_controller.py` 的坐标轮询。
- 当前合并结果：生产配置采用 `edge_gap_mm=2.0`，模板分配使用 `target_scale=1.03`，队列为 `P4→P3→P2→P1`。单片顺序为 pick-ready → descend → magnet ON → lift → rotate → transit → place-ready → descend → magnet OFF → done-lift；时长采用 `1500/800/800/1200 ms` 基准和 `200 ms` settle。三组实拍全部规划成功，Mock 确认非零 roll 单片共下发八条 `set_pose`，磁铁切换位于两个低位动作之后。
- 可信等级：A（两套源码、哈希、三组实图离线执行与 Mock 轨迹）+ D（队友实机效果与合并策略）；是否需要实机验证：需要。
- 最后核查时间：2026-07-31。

## F-038 当前 Q1 transfer 已对齐 pintu 的实际主执行链

- 来源确认事实：`pintu/jetson_to_nexarm/puzzle_runner.py::PuzzlePickPlaceRunner.execute_one` 的实际顺序为 pick-ready、descend-pick、magnet ON、lift、rotate-in-air、transit、place-ready、descend-place、magnet OFF、done-lift；默认 approach 为 40 mm、transit Z 为 120 mm，move/descend/lift/rotate 基准时长为 `1500/800/800/1200 ms`，settle 为 200 ms。旋转小于 1° 时跳过，其他角度按 `max(400, base*max(0.5, abs(delta)/90))` 分配时长。
- Q1 实现事实：`q1/motion.py::plan_single_move` 生成 pick-ready、rotate 和 transit 位姿；`q1/executors/nexarm.py::execute_single_move` 直接执行上述顺序。固定 BUFFER、25% XY 斜向 clearance 和每段 1 秒 settle 已从生产链移除。
- 离线结果：三组实拍 `20260730_232827_207582`、`20260730_233201_481210`、`20260730_233351_970591` 均保持 `scene_valid=true` 并生成 `P4→P3→P2→P1`。Mock 非零 roll 单片下发八条 `set_pose`，事件顺序确认磁铁在吸取低位完成后开启、释放低位完成后关闭。
- 可信等级：A（pintu/Q1 源码、实图离线规划和 Mock）+ D（采用队友轨迹作为当前项目决策）；是否需要实机验证：需要，尚未连接 NexArm、未给电磁铁通电、未同步 Jetson。
- 最后核查时间：2026-07-31。

## F-039 Q1 纸面到机械臂标定已含接触面 Z 平面

- 结论：2026-07-31 晚间四点触地测量拟合得到新 `paper_to_robot_matrix` 与 `surface_z_plane_mm`。纸面中心映射约 `(240.0, 8.5)`。`ArmCoordinateMapper.paper_to_robot` 在加载平面后对 3×3 矩阵路径按 `z=height+(plane(x,y)-plane(ref))` 补偿接触面倾斜；`pick_height`/`release_height` 只表示参考点 `(105,148.5)` 的绝对 Z。
- 现行参数：以 `2026E/q1/config/robot_config.json` 为准（当前平面约 `[0.04,-0.005,-33.25]`，`pick_height=-12`，`release_height=-8`）。原始四点最小二乘斜率约 `0.0643` 已在 `2febb608` 及后续微调中下调。
- 来源：用户四点 XYZ 与图像像素（D）；`calibration.py`、`source_facts.json::q1_arm_calibration`（A）。
- 可信等级：A+D；是否需要实机验证：需要。
- 最后核查时间：2026-07-31。

## F-040 Q3 扑克牌拼图已接入 Q1 正式硬件主链

- 赛题事实：`docs/E题_拼图装置.pdf` 第 2 页规定现场碎片不超过 4 片、每片不超过 5 边、每边不小于 20 mm、每片至少一边属于外框，成品矩形长边为 90–120 mm、短边为 50–90 mm；扑克牌题还要求牌面花纹对应。来源类型为正式赛题资料，可信等级 B。
- 算法事实：`2026E/q3/card_solver` 来自 `2026E-7.31/q3/card_solver`；除 `image_input.py` 新增“接收已矫正 A4 图”适配器及 `__init__.py` 导出外，其余算法文件保持同源。`CardPuzzleSolver` 使用无缩放、无镜像的刚体搜索，并以 Lab、红黑前景、线连续性、角标和对称性评价花纹拼接。来源类型为源码，可信等级 A。
- 集成事实：`q3/analyzer.py::CardSceneAnalyzer.analyze` 复用 Q1 的 `detect_paper/rectify_paper`，将横拍 A4 统一为 `210×297 mm` 竖向纸面坐标；`q3/motion.py::plan_card_moves` 将求解结果转成 Q1 `SingleMovePlan`。相机、手眼标定（含 `surface_z_plane_mm`）、最大内接吸点、NexArm executor、摆臂 roll 补偿、STM32 磁铁会话及 `q1/config/robot_config.json` 均直接复用，不在 Q3 内复制矩阵或高度。
- 离线证据：正式算法副本通过队友可用测试 `22 passed, 11 skipped`；合成图得到 4 片、约 `99.12×69.21 mm` 成品、4 个完整动作和 `capture.png/plan.png/scene.json/piece_moves.json`；Mock 控制器完成初始化、单次拍照、4 片执行、最终 HOME 和关闭；`q3/tests/test_q1_calibration_reuse.py` 确认 Q3 规划位姿继承最新接触面 Z 补偿。可信等级 A；实机成像、抓放及花纹方向仍需验证。
- 最后核查时间：2026-07-31。
