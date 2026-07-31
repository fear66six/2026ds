# 项目工程决策

本文件只记录项目主动选择，不把工程策略写成厂商事实。

## D-001 采用“原件 + 轻量人工文档 + 可重建索引”的资料管理方式

- 决策：保留原始资料，只维护导航、长期事实、工程决策和实机待确认四类轻量文档；检索内容由 `.cache/docs_index/` 自动生成。
- 原因：避免重复抄录 API/协议造成版本漂移，同时让每个结论可追溯。
- 替代方案：维护大型统一技术手册；为全文检索部署数据库或搜索服务。
- 依据：项目实际包含 PDF、ZIP、源码、固件和图纸等多种原件，且存在副本与多版本候选。
- 影响范围：全部后续开发与资料维护任务。
- 当前状态：已采用。
- 需要重新评估的条件：资料规模或多人协作需求超过轻量 JSON 索引能力。

## D-002 K230/CanMV 工程保留为参考，不作为 Jetson/NexArm API 的替代来源

- 决策：不删除或批量改写 `TaskSuite_E/` 和 K230/WonderMK 资料；需要 Jetson 或 NexArm 接口时重新查对应原件，不跨平台套用。
- 原因：现有工程真实包含 K230/CanMV 代码，但板端和 NexArm 资料属于不同设备边界。
- 替代方案：直接在 K230 工程上覆盖成 Jetson 实现；把 K230 API 包装为通用接口而不核查硬件。
- 依据：`TaskSuite_E/README.md` 与 `TaskSuite_E/k230/`；`docs/板端/`；`docs/NexArm机械臂/1.教程资料/6. 外部主控二次开发/`。
- 影响范围：视觉、UI、通信和硬件抽象层。
- 当前状态：已采用。
- 需要重新评估的条件：项目正式确认继续使用 K230 作为主视觉平台，并形成新的有证据决策。

## D-003 所有真实硬件访问默认禁用并要求 Mock 与安全关闭

- 决策：后续新增硬件代码不得在 import 或构造阶段连接设备；默认走 Mock，运动/通电需要多重显式授权，并实现异常和超时关闭。
- 原因：机械臂、电磁铁、GPIO、串口和烧录都可能造成设备损坏或人身风险，资料也尚未确认当前实机配置。
- 替代方案：沿用厂商 Demo 的即运行即连接模式。
- 依据：项目安全规则；现有 NexArm SDK 的 `_ensure_open()`/`_ensure_connected()` 会在调用方法时隐式连接，因此项目封装层必须额外隔离。
- 影响范围：NexArm、Jetson GPIO、STM32、电磁铁、继电器/MOSFET 和测试脚本。
- 当前状态：已采用。
- 需要重新评估的条件：不取消默认安全策略；仅可为受控测试增加经用户批准的分层解锁流程。

## D-004 STM32 电磁铁控制采用 USART1 和 PB12，不开发 USB CDC

- 决策：运行链路采用 Jetson USB 转 ATK-MO340P USB-TTL，再接 STM32F103C8T6 USART1；PA9/PA10 使用 115200、8N1，PB12 作为 MOSFET 控制输出，软件按高电平开启、低电平关闭设计。不开发 USB CDC，不使用 PC13 或 PWM 控制 MOSFET。
- 原因：用户已确定最终通信与控制架构；USART1 系统 Bootloader 也已通过当前 ATK-MO340P 链路完成只读连接和 Flash 备份。
- 替代方案：USB CDC；PC13 控制；继电器或 PWM；这些方案本轮不采用。
- 依据：用户当前工程决策；`docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板硬件资料/STM32F103C8T6-MICRO-原理图.pdf` 第 1 页；`logs/stm32_uart_bootloader/connection_115200.log`。
- 影响范围：`firmware/stm32f103_uart_magnet/`、`drivers/stm32_magnet_uart.py`、后续 Jetson 串口集成与电气验证。
- 当前状态：该决策描述的是历史 C8T6/`PB12` 架构。现行板卡、工程路径与控制脚已由 D-038 / F-028 更新为 STM32F103VET6 + PC0。
- 需要重新评估的条件：实际 MOSFET 模块空载测试证明输入极性或 3.3 V 兼容性与该决定不符，或硬件架构改变。

## D-005 Q1 生产入口仅暴露真实摄像头 + NexArm + STM32 电磁铁闭环

- 决策：`2026E/q1/main.py` 不再提供 `simulate`、`dry-run`、人工移动或 `--image` 离线入口；仅构建 `SnapshotCamera + NexArmRobotExecutor + STM32MagnetController`。仿真/Mock 模块保留在包内供离线测试，但不得从生产 CLI 触发。
- 原因：赛题实机调试需要单一真实路径，避免误用仿真画面或人工代替机械臂；同时遵守 D-003 的多重硬件门禁。
- 替代方案：继续保留 dry-run/人工模式作为默认调试入口。
- 依据：`2026E/q1/main.py`；`2026E/q1/runtime_config.py::real_run_blockers`；用户 2026-07-29 确认。
- 影响范围：Q1 运行方式、文档与测试策略（`tests/q1/` 仅离线回归）。
- 当前状态：已采用。
- 需要重新评估的条件：需要经批准的受控 dry-run 分层解锁流程时另立决策。

## D-006 Q1 纸面内旋转映射到 NexArm roll，参数来自 arm_calibration

- 决策：单块规划区分 `pick_roll_deg` 与 `release_roll_deg`；吸取后在安全高度旋转腕部。`arm_calibration` JSON 必须提供 `wrist_roll_zero_deg`、`wrist_roll_sign`、`wrist_roll_min_deg`、`wrist_roll_max_deg`，缺一则禁止 RealRun。越界时返回 `WRIST_ROTATION_OUT_OF_RANGE`，禁止静默 clamp。
- 原因：用户确认 roll 控制纸面内旋转；碎片真正旋转发生在吸取后的腕部变化。
- 替代方案：同一 roll 贯穿全部位姿；静默截断（已否决）。
- 依据：`2026E/q1/motion.py`；`2026E/q1/wrist.py`；`2026E/q1/calibration.py::map_in_plane_rotation`；NexArm SDK `set_pose(...)`。
- 影响范围：Q1 运动规划、机械臂标定文件格式、实机验证项。
- 当前状态：已采用；腕部映射尚未实机标定。
- 需要重新评估的条件：实机低速测试证明 roll 并非纸面内旋转轴或需改用其他姿态字段。

## D-007 Q1 采用全局模板分配、精确边拟合与绝对放置判定

- 决策：静态分析对 N 个候选枚举 C(N,4)×4! 全局分配；`approxPolyDP` 仅作粗顶点，最终顶点由稳健直线拟合求交；刚性变换返回完整 R、t；放置判定使用 A4 全局毫米绝对顶点误差；选择器使用真实几何评分。
- 原因：检测常出现 4～7 个候选，旧前 N 截断与轮廓顺序不可靠；approxPolyDP 顶点精度不足。
- 替代方案：取面积最大四块；用 minAreaRect 角度（已否决）。
- 依据：`2026E/q1/puzzle_solver.py::assign_templates_global`；`edge_refinement.py`；`geometry.py::compute_rigid_transform`；`tests/q1/test_geometry_optimization.py`。
- 影响范围：Q1 视觉分析、运动规划、审计恢复、选择器评分。
- 当前状态：已采用（离线测试通过）；实机参数见 `docs/TODO_VERIFY.md`。
- 需要重新评估的条件：实机电磁铁吸取点偏离几何中心需改 `pick_point_source_mm` 定义时。

## D-008 Q1 正式图像链路唯一采用 K230 TTL 请求式 JPEG

- 决策：生产图传仅保留 Hiwonder K230 UART3 TTL → Jetson CH343；固定 460800、1280×720、quality=65、discard=2、chunk=4096；协议 V2；Jetson API 为 `K230TtlSnapshotCamera`。不采用 UVC/`/dev/video0`、HDMI、Wi-Fi、K230 原生 CDC JPEG，也不在运行时切换其它分辨率/波特率。K230 SD 文件由人工部署。
- 原因：实测在 460800+720p 稳定可用；多套图传实现并存会造成参数漂移与启动竞态。
- 替代方案：USB CDC / UVC / 降波特率或降分辨率兜底（已否决为生产路径）。
- 依据：`2026E/drivers/k230_ttl_camera/`；`docs/interfaces/k230_ttl_camera/`；F-013；用户确认人工放置 K230 代码。
- 影响范围：Q1 `--camera-backend k230_ttl`、观察位稳定后再 `capture_snapshot()`。
- 当前状态：已采用；链路烟雾与 100 次压测通过。
- 需要重新评估的条件：换 TTL 适配器导致 by-id 变化，或赛题改用其它相机硬件。

## D-009 Jetson Q1 使用唯一根目录和独立安全复位门禁

- 决策：Jetson 唯一项目根目录为 `/home/jetson/2026E`；硬件实现集中到 `hardware/`，旧路径只保留符号链接。复位测试仅由 `python3 -m q1.scripts.test_camera_arm_reset` 执行；无精确 `RUN_ARM_RESET` 时只做检查和 K230 预热抓图。
- 决策：复位测试最初使用独立 HOME/OBSERVE；按用户 2026-07-30 确认，复位测试仅保留 `home_pose` 作为唯一复位/拍照位，删除 `arm_reset.json` 中的 `observe_pose`。当前 HOME 候选由 D-011 给出。claw 安全覆盖为 0，动作时长为 6000 ms，并配置全局加速度 10；该加速度数值语义标为待实机验证。
- 原因：当前 K230 已成为末端负载的一部分，用户确认 pitch=0° 时镜头水平向前，无法观察 A4 纸；并确认复位测试中观察位与 HOME 应为同一点。同时避免旧 1500 ms 参数和未确认运动，不引入电磁铁或完整 Q1 状态机。
- 依据：`TaskSuite_E/Robot_Arm.cpp::reset_all`；Jetson `hardware/nexarm/jetson_to_nexarm/arm_controller.py`；`q1/config/arm_reset.json`；用户确认。
- 影响范围：Jetson 目录、K230/NexArm 适配、机械臂复位测试和运行产物。完整 Q1 的 `runtime_config.observe_pose` 仍保留，不由本复位配置自动删除。
- 当前状态：复位测试已改为仅 HOME；新 HOME 候选尚待低速验证。
- 需要重新评估的条件：低速实测证明 pitch=-90° 不是当前相机垂直向下方向、线缆/支架在该姿态干涉、当前 NexArm 固件的全局加速度标度变化或安装姿态变化。

## D-010 安全复位到位位置容差采用 7 mm

- 决策：仅对 `q1.scripts.test_camera_arm_reset` 的固定 HOME 安全复位，将三维合成位置容差由 5 mm 调整为 7 mm；继续要求姿态误差不超过 3°且连续 3 次反馈合格，不放宽工作区、动作时长、加速度或人工确认门禁。
- 原因：首次 6000 ms 低速 HOME 实测最终反馈为 `(195,4,200)`，相对目标 `(200,0,200)` 的合成残差为 6.40 mm；随后无运动读取为 `(195,3,199)`，合成残差为 5.92 mm，说明机械臂已稳定停止但原 5 mm 门限低于当前实机重复反馈残差。
- 替代方案：保持 5 mm 并持续超时；按每轴独立容差判定；直接扩大到更高容差。后两者本轮不采用。
- 依据：Jetson 运行报告 `output/runs/20260730_013618_569613/report.*`、`output/runs/20260730_013740_718035/report.*`；`2026E/q1/robot/safe_nexarm.py::wait_until_idle`；用户 2026-07-30 明确批准 7 mm。
- 影响范围：`2026E/q1/config/arm_reset.json` 的安全复位到位判定；不自动适用于完整 Q1 的抓取、放置或视觉精度。
- 当前状态：配置已调整，尚待重新执行固定低速 HOME 到位验证。
- 需要重新评估的条件：误差超过 7 mm、误差持续漂移、安装负载变化，或完整 Q1 标定得到更严格且可重复的到位模型。

## D-011 HOME 采用 A4 构图候选，复位测试不再单独保留 OBSERVE

- 决策：A4 构图 HOME 候选最初调整到 `(150,0,230,-93,0,0)`；该阶段的范围扩展和实测现由 D-014 的下一候选继续推进。用户确认复位测试中 `observe_pose` 与 `home_pose` 应为同一处，因此删除 `arm_reset.json` 的独立 `observe_pose`，固定低速序列只到达 HOME、稳定后拍照。
- 原因：用户判断需要降低 x、提高 z，以扩大并平移 A4 在画面中的覆盖余量；并确认不需要独立观察位。
- 替代方案：保留独立 OBSERVE；先使用原安全边界 `(180,0,210,-90,0,0)`。用户未选择。
- 依据：用户提供的当前测试图片；`2026E/q1/config/arm_reset.json`；`q1/scripts/test_camera_arm_reset.py`；用户 2026-07-30 明确批准。
- 影响范围：仅复位测试配置与脚本；完整 Q1 的 `runtime_config.observe_pose` 仍单独存在，待后续实机确认是否与 HOME 统一。
- 当前状态：pitch=-93° 候选已实测但未进入到位容差，构图仍裁切 A4 上下边界；下一候选见 D-014。
- 需要重新评估的条件：支架/线缆扫掠干涉、目标不可达、误差超过 7 mm、A4 构图变差，或正式 Q1 仍需要不同于 HOME 的观察高度。

## D-012 正式 Q1 观察位与复位 HOME 统一

- 决策：正式抓放闭环的观察/回观察位与复位 `home_pose` 始终使用同一候选；当前值由 D-015 更新为实测可达停止位 `(173,4,226,-84.4,0,0)`。`safety_config` 优先写 `home_pose`，`observe_pose` 仅作同义别名。`NexArmRobotExecutor.move_to_observe_pose` 单次直接到位，不使用 TaskSuite 先到 Z=200 再下降的路径；claw 固定为 0，默认时长 6000 ms（可被 `move_duration_ms` 覆盖）。
- 原因：用户确认复位与正式拍照应为同一构图点；相机安装后旧 OBS_Z=160 / claw=-60 / 1500 ms 路径不适用。
- 替代方案：继续保留独立更低观察位。用户否决。
- 依据：`q1/config/arm_reset.json`；用户 2026-07-30 明确要求；`q1/runtime_config.py`、`q1/main.py`、`q1/executors/nexarm.py`。
- 影响范围：正式 Q1 RealRun 观察运动与 safety JSON 字段约定；不自动证明该点已构图合格或物理安全。
- 当前状态：代码与示例已改为统一 HOME；当前值取自实测可达停止位，A4 旋转 90° 后的构图仍待验证。
- 需要重新评估的条件：实机证明需要不同于 HOME 的观察高度，或当前高度仍无法稳定覆盖 A4。

## D-013 HOME 到位超时时保留构图证据

- 决策：复位命令超过硬超时后不发送任何进一步运动，但读取一次最终反馈并抓拍 `home_timeout.jpg`，同时保持运行状态为失败。
- 原因：原逻辑只在到位判定成功后拍摄 `home.jpg`，导致位置或姿态略超容差时无法获得实际停止位置的构图证据；预检 `warmup.jpg` 是运动前画面，不能用于 HOME 调参。
- 依据：运行报告 `20260729_122043_166630`；`q1/scripts/test_camera_arm_reset.py`。
- 影响范围：仅故障取证，不改变到位容差、不放行失败位姿、不发送恢复动作。
- 当前状态：已由运行 `20260729_123051_357485` 验证，超时后成功生成 `home_timeout.jpg`，且未发送后续运动。

## D-014 HOME 下一候选扩展到 z=300、pitch=-96，位置容差保持 7 mm

- 决策：将统一 HOME/正式观察候选改为 `(150,0,300,-96,0,0)`，复位测试 z 上限扩展为 300、pitch 下限扩展为 -96；`position_tolerance_mm` 明确保留 7.0，不因候选超出到位能力而放宽。
- 原因：`(150,0,230,-93,0,0)` 实测最终反馈为 `(165,4,220,-86.6,0,0)`，超时图显示 A4 上下边界仍超出画面；用户要求提高到 z=300，并选择 pitch 再降低 3°以继续校平镜头。
- 替代方案：只提高到 z=250；按前两次反馈线性外推到 pitch=-108。用户分别否决或未选择。
- 依据：运行报告 `20260729_123051_357485`、`home_timeout.jpg`、用户 2026-07-30 明确选择。
- 影响范围：复位测试与正式 Q1 统一观察位、软件工作区；不证明 z=300 / pitch=-96 物理可达。
- 当前状态：`(150,0,300,-96,0,0)` 已实测不可达；由 D-015 覆盖。
- 需要重新评估的条件：目标不可达、异常运动、线缆受拉、A4 仍无法完整入画，或实际 pitch 对命令响应继续饱和。

## D-015 HOME 改用实测可达停止位，并与软件安全范围分离

- 决策：放弃不可达候选 `(150,0,300,-96,0,0)`；将统一 HOME/正式观察位改为运行 `20260729_124259_493009` 的实测停止位 `(173,4,226,-84.4,0,0)`。复位测试 `workspace_limits` 改为 `x[150,200]`、`y[-20,20]`、`z[200,250]`、`pitch[-90,-80]`，使 HOME 不贴边并保留余量；`position_tolerance_mm` 仍为 7.0。
- 原因：`(150,0,300,-96)` 实测仅有毫米级漂移且出现“响一下几乎不动”，更像逆解/关节不可达而非软件门禁。用户已将 A4 旋转 90°，并要求 HOME 与安全范围不要重叠。
- 替代方案：继续加大 z/pitch；仅为通过判定放宽位置容差。两者均否决。
- 依据：报告 `20260729_124259_493009`、超时图、厂商示例中 `z` 高位通常不与 `pitch=-90` 同用、用户 2026-07-30 确认。
- 影响范围：复位测试与正式 Q1 统一观察位；镜头是否平行桌面取决于当前安装与该可达姿态，不能由不可达 pitch 命令强求。
- 当前状态：运行 `20260729_125749_401725` 已验证 XYZ 可达，实际 `(174,2,227,-83.7)`，位置误差 2.45 mm，A4 旋转后完整入画；梯形透视仍待调整。
- 需要重新评估的条件：该可达位仍无法拍全 A4、需要改相机安装角、或后续找到可重复验证的更高可达点。

## D-016 保留可达 XYZ，将 HOME pitch 调为 -90°

- 决策：统一 HOME/正式观察位从 `(173,4,226,-84.4,0,0)` 调为 `(173,4,226,-90,0,0)`；pitch 软件范围由 `[-90,-80]` 扩展为 `[-95,-80]`，使 -90° 不贴边。位置容差保持 7 mm，XYZ 和其他参数不变。
- 原因：旋转后的 A4 已完整入画，但边框测量显示下边约比上边宽 10%，左右边长度接近、水平边倾斜不足约 1°，更符合 Pitch 方向不平行，而非 Roll 或主要镜头径向畸变。该次实际反馈 pitch 为 -83.7°，距 -90° 约 6.3°。
- 替代方案：只用透视标定修正；继续修改 Z；物理调整相机支架。先测试小范围 pitch 修正，再决定是否需要支架调整。
- 依据：运行 `20260729_125749_401725` 的 `home.jpg`、报告实际位姿与边框直线测量；用户 2026-07-30 批准。
- 影响范围：复位测试与正式 Q1 统一观察位；不改变纸面透视标定的必要性。
- 当前状态：低速复测失败：发送 `(173,4,226,-90,0,0)` 后反馈持续为 `(183,3,220,-85.7,0,0)`，没有发生可确认运动；程序在 HOME 超时后未继续下降。该候选已由实测结果否决，统一 HOME 恢复为 D-015 的 `(173,4,226,-84.4,0,0)`。
- 需要重新评估的条件：-90° 在当前 XYZ 不可达、梯形未改善或反向、线缆受拉，或相机光轴相对末端存在固定安装偏角。

## D-017 Q1 采用三档令牌门禁与模拟磁铁完整轨迹

- 决策：D-005 的“生产 CLI 不暴露模拟后端”由本决策更新。无 `--confirm` 时只允许 K230 拍照、分析和规划，绝不初始化 NexArm；`RUN_Q1_HOME` 只允许机械臂到统一 HOME 后拍照分析；仅 `RUN_Q1_ARM` 允许逐片抓放轨迹。电磁铁默认 `SimulationMagnetController`，该模式仍执行真实臂接近/下降/抬升/转运/释放轨迹，但只记录 HOLD/OFF 事件，报告固定为 `physical_pick_verified=false`。
- 决策：队友 PC 流程的一次四片规划仅保留为 `four_piece_advisory.json`；生产执行继续每轮一片、回 HOME、视觉复核，不采用 MCU G-code 或四片开环批量执行。
- 决策：生产执行器在任何位姿指令前必须完成固件版本和当前六维位姿握手，并下发已批准的低全局加速度 10；握手失败时不得发送运动。
- 原因：当前任务需要在真臂上验证完整状态机轨迹，同时真电磁铁尚未接入；令牌分层防止分析命令意外运动，也避免把模拟磁铁结果误报为真实吸取成功。
- 依据：用户 2026-07-30 明确批准；`2026E/q1/main.py::dispatch`；`controller.py`；`planning_advisory.py`；`executors/nexarm.py`。
- 影响范围：Q1 CLI、运行报告、Jetson 同步和现场操作流程。
- 当前状态：实现与离线回归通过；低高度真臂路径仍由 V-013 阻止直接视为已验证。
- 需要重新评估的条件：真电磁铁完成硬件与安全验证，或低高度逐点标定改变当前安全路径。

## D-018 Q1 改为单一正式闭环入口与单一机械臂配置

- 决策：D-017 的三档入口由本决策覆盖。删除无确认分析、`RUN_Q1_HOME` 和 `RUN_Q1_ARM` 三种生产逻辑；唯一正式令牌为 `RUN_Q1`，缺少精确令牌时在打开硬件前拒绝启动。
- 决策：正式闭环固定为 HOME → 拍照分析 → 审计 → 单片规划 → Z250 接近 → Z25 吸取 → 抬升/旋转/搬运 → Z25 释放 → 抬升 → HOME → 视觉复核。每轮只执行一片。
- 决策：机械臂端口、HOME、纸面到机械臂矩阵、腕部、高度、速度/加速度、到位容差和工作区只保存在 `2026E/q1/config/robot_config.json`。位置到位容差按用户最新确认由 7 mm 改为 10 mm；姿态容差和工作区不扩大。
- 依据：用户 2026-07-30 明确确认；`q1/main.py`、`controller.py`、`executors/nexarm.py`、`config/robot_config.json`。
- 当前状态：本地实现完成，待离线回归和 Jetson 同步验证。

## D-019 A4 四角仅由 detect_paper 实时检测

- 决策：删除正式路径中的静态 `paper_calibration` JSON、`--paper-calibration` CLI 与 `PaperCalibration` 类。A4 四角像素只能由每帧 `vision.detect_paper` 从实图检测；检测失败则本轮场景无效。纸面到机械臂矩阵、腕部与高度仍来自 `robot_config.json`。
- 原因：用户确认纸面边界不应提前人工点选，而应由实际图像判断。
- 依据：用户 2026-07-30 明确要求；`q1/analyzer.py`、`q1/vision.py::detect_paper`、`q1/main.py`。
- 影响范围：视觉入口、RealRun blockers；运行产物保存实时检测的 `paper_frame.json`，并按该帧四角生成仅用于审计的 `rectified.png`。
- 当前状态：2026-07-30 使用实拍运行 `20260729_133130_779823`、`20260729_133425_944773` 离线回放确认横放 A4 左边界约为 `x=161`，四块均可分配为 P1–P4。已删除旧 K230 构图不适用的 18% 左裁边，并按纸面坐标审核横放时的左/右分区；后续仍需观察多轮角点抖动。
- 需要重新评估的条件：自动检测在正式构图下反复失败或角点抖动导致规划误差过大。

## D-020 运行目录必须在终端立即且重复输出

- 决策：`RunRecorder` 创建目录后立即以稳定键名输出绝对 `Q1_RUN_ID`、`Q1_RUN_DIR` 和 `Q1_RUN_EVENTS`；失败、关闭和成功时重复输出对应目录，并在运行根维护 `LATEST_RUN.txt`。
- 原因：MobaXterm 中间输出可能滚动或异常终止，用户需要快速定位本次日志，不能只依赖成功结束时的一行相对路径。
- 依据：用户 2026-07-30 明确要求；`q1/controller.py::RunRecorder`、`q1/main.py::main`。
- 影响范围：仅终端可观测性和最近运行指针，不改变视觉、规划或硬件动作。
- 当前状态：已实现，待 Jetson 输出验证。

## D-021 HOME 与安全高度上调 15 mm（已回退）

- 决策：为改善相机拍全 A4 的构图，将统一 HOME/观察位由 `(173,4,226,-84.4,0,0)` 调为 `(173,4,241,-84.4,0,0)`，`safe_height` 由 Z250 调为 Z265，正式工作区 Z 上限由 260 调为 275 mm，继续保留 10 mm 软件余量。
- 原因：用户现场反复出现 A4 边缘拍不全，导致 `detect_paper` 不稳定。
- 依据：用户 2026-07-30 明确要求；`2026E/q1/config/robot_config.json`。
- 影响范围：拍照 HOME、每次安全抬升/转运高度及 Z 工作区；不改变抓取/释放 Z25、XY 映射、pitch 或腕部参数。
- 当前状态：实测目标 `(173,4,241,-84.4,0,0)` 最终反馈 `(168,5,219,-86.9,0,0)`，位置误差 22.58 mm，程序按门限停止且未发送恢复动作。用户随后批准回退，正式配置恢复 HOME Z226、safe Z250、工作区上限 Z260；A4 构图问题改由纸张位置或相机安装处理。

## D-022 正式抓放改用完整六维目标，不再构造分轴航点

- 决策：D-018/D-021 中的 Z250 安全高度以及“源 XY/Z226 后再下降”路径均由本决策覆盖。正式单片执行只发送两个完整目标：HOME 直接到源 `(x,y,25,pitch,pick_roll,claw)`，再直接到目标 `(x,y,25,pitch,release_roll,claw)`；不再构造原地抬升、源上方、竖直下降、转运高度、竖直释放或释放后抬升航点。`motion_mode=direct_pose` 是正式门禁条件。
- 决策：任何已发送的 `set_pose(..., duration_ms)` 至少等待完整 `duration_ms` 后，才允许用连续稳定反馈宣布到位并发送下一位姿；不得因为旧反馈已落入10 mm容差而提前完成。
- 原因：运行 `20260729_134450_208600`、`20260729_134517_829094` 均在第一条原地 Z250 命令超时；随后 `20260729_135642_047211`、`20260729_135719_628157` 又在源 XY/Z226 航点超时，各次约 47 个反馈样本始终保持 `(168,5,219,-86.9,0,0)`。用户指出当前机构不适合固定 XY 分轴升降，并要求使用厂商已封装的完整坐标运动。
- 依据：上述四次运行的 `events.jsonl`、`failure.json`、`single_move_plan.json`；Hiwonder `UART_Control/nexarm_sdk.py::set_pose`（第296行，一条 `CMD_COORDINATE_SET` 同时编码六维目标与时长）；`UART_Control/basic_demo.py` 第58行；`q1/executors/nexarm.py`；用户 2026-07-30 现场确认。
- 当前状态：本地实现与离线回放通过；直接到 Z25 的每个完整 XY/Z/Pitch/Roll 组合仍未实机验证，不能由 SDK 支持该命令外推为机构必然可达。

## D-023 重复无运动后冻结 Z25 抓放并补齐规划残差门禁

- 决策：运行 `20260729_141607_088180`、`20260729_141721_922896` 的两个源 Z25 完整目标在约 12 秒内均无任何可观察位移，因此 `direct_pick_release_pose_verified=false` 成为正式配置事实。Q1 仍可到 HOME、拍照、审计和保存规划，但在该字段经独立实机标定确认前不得发送抓放位姿。
- 决策：`plan_single_move` 必须以 `vertex_max_error_mm=8.0` 检查刚体变换最大残差；超过门限直接报 `PLAN_GEOMETRY_RESIDUAL`，不得进入真实运动。首个一一匹配成功的 HOME 场景锁定本次运行的 A4 边界，后续检测只用于漂移审核，超过 `paper_corner_drift_limit_px` 时重新分析而不静默改坐标系。
- 决策：运动尝试必须区分 `REACHED_WITH_FEEDBACK_CHANGE`、`ALREADY_IN_TOLERANCE_NO_FEEDBACK_CHANGE`、`NO_FEEDBACK_CHANGE_TIMEOUT`、`TIMEOUT_AFTER_FEEDBACK_CHANGE` 与 `STALE_FEEDBACK_HARDWARE_FAULT`（见 D-028）。处于 HOME 容差内但反馈未变化，不得再被报告为该命令已证明机械运动正常。
- 原因：两次 P3 刚体拟合最大残差分别为 18.34 mm、18.06 mm，均明显超过 8 mm；旧规划仅检查非镜像解。两次 Z25 命令的反馈均固定为 `(168,5,219,-86.9,0,0)`，延长超时或放宽容差不能解决。
- 依据：上述两次运行的 `failure.json`、`single_move_plan.json`、`selection.json`、`raw.png` 和 `overlay.png`；`q1/motion.py`、`q1/executors/nexarm.py`；Hiwonder UART `nexarm_sdk.py::set_pose`。Jetson SDK 与项目内厂商 SDK 的 `set_pose` 实现相同，仅 `serial` 导入位置不同。
- 当前状态：本地测试、两次实拍离线回放及 Jetson 无运动检查通过；实际可达的装载相机/磁铁末端抓取位姿仍待独立标定。由 D-028 覆盖旧“运动观察”命名与独立标定入口。

## D-024 自备纯色四片采用整图水平镜像目标

- 决策：第1问当前自备纯色四片的目标布局设为 `TARGET_LAYOUT_MODE=mirror_x`。这是对完整 10×6 cm 目标拼图做一次水平镜像；每一块的规划仍必须满足 `det(R)>0`，禁止以单块反射冒充机械臂可执行运动。
- 原因：运行 `20260729_143453_743075`、`20260729_143522_372571` 中四块实物相对题图模板均呈一致反面手性。旧目标下 P1/P2/P3/P4 最大刚体残差约为 `10/26/18/14 mm`；整图镜像后，第一组实拍的纯旋转残差降为 `4.25/4.37/2.26/0.76 mm`。两次实际被选中的 P3 分别降到 2.265 mm 和 2.394 mm。
- 依据：`docs/E题_拼图装置.pdf` 第2页图2（厂商/赛题正式原图，B）；上述两次运行的 `raw.png`、`scene.json`（实机工程证据，D）；`q1/pieces.py::template_target_vertices_mm`、`q1/geometry.py::compute_rigid_transform`（源码，A）。
- 适用边界：只适用于当前自备纯色四片和第1问“拼成目标矩形”。扑克牌花纹题或现场未知碎片不得沿用该镜像决定，必须根据正面花纹/现场目标重新建模。
- 当前状态：离线回放和回归测试通过，已同步 Jetson；机械抓取位姿仍由 D-023 门禁独立阻止。

## D-025 单目标可达性测试取消按 Z 逐级依赖（历史；入口已删除）

- 决策（历史）：`source_z180` 至 `source_z25` 的每个完整位姿曾作为独立候选；到位区分 `REACHED_WITH_FEEDBACK_CHANGE`、`ALREADY_IN_TOLERANCE_NO_FEEDBACK_CHANGE`、`NO_FEEDBACK_CHANGE_TIMEOUT` 和 `TIMEOUT_AFTER_FEEDBACK_CHANGE`；反馈变化只描述遥测。
- 原因：运行 `20260729_150141_324127` 向 `(246,35,180,-84.4,0,0)` 发送命令后反馈不变；HOME 运行 `20260729_150156_354380` 因起始误差 8.66 mm 被旧逻辑误标 `REACHED`。`TaskSuite_E` 历史低位目标说明笛卡尔可达性不随 Z 单调。
- 依据：上述两个 Jetson `report.json`（A）；`TaskSuite_E` 相关源码（A）；当时的 `calibrate_single_pose` / `safe_nexarm`（已由 D-028 删除或收紧）。
- 适用边界：运行 `20260729_153642_988359` 中用户看到运动但反馈停在 HOME，正式 `direct_pick_release_pose_verified` 不因测试门禁调整自动解除。
- 当前状态：独立标定入口与配置块已删除；仅保留该 Z25 冲突证据目录。后续验证走 D-028 生产执行器路径。

## D-026 真实电磁铁采用 STM32 限时租约并由显式后端启用

- 决策：生产抓放时序为源位姿新鲜反馈确认 → `MAGNET_ON`/状态确认 → 释放位姿新鲜反馈确认 → `MAGNET_OFF`/状态确认。D-026 中曾将 `direct_pick_release_pose_verified` 置 true 的部分由 D-028 覆盖回 false。
- 决策：端口、500 ms 租约、吸合/释放等待集中在 `q1/config/robot_config.json`。
- 决策：续租、串口或状态异常立即阻止后续位姿，尽力 `EMERGENCY_OFF` 并关闭通信。
- 依据：`firmware/stm32f103_uart_magnet/src/main.c`、`magnet_control.c`（A）；`drivers/stm32_magnet_uart.py`（A）；F-011 的应用通信实测（A）；STM32 by-id 路径来自用户（D）。
- 适用边界：`STATUS MAGNET=1/0` 只证明 STM32 软件/PB12锁存状态，不证明线圈电流、磁力、吸住或物理释放。`physical_pick_verified` 在视觉确认真吸取前保持 `false`。

## D-027 生产 Q1 取消模拟磁铁后端

- 决策：D-017 与 D-026 中“生产入口允许或默认 sim”的部分由本决策覆盖。`q1.main` 只接受 `magnet_backend=stm32`，默认即为 `stm32`；传入 `sim` 在打开硬件前由参数解析拒绝。`SimulationMagnetController` 已从生产模块删除，Mock 仅保留在离线驱动测试中。
- 决策：用两个不同字段避免误解：`physical_pick_enabled=true` 表示真实 STM32 上电路径已启用；`physical_pick_verified` 是运行证据状态。真实动作后的下一轮视觉审计仅在上一模板为 `PLACED_OK` 时将其更新为 true，并保存 `cycle_xx/physical_pick_verification.json`。
- 原因：用户 2026-07-30 明确要求 Q1 全流程真实实现、不再保留任何生产信号仿真，同时要求真实到源上电、到目标断电。
- 依据：用户明确决策（D）；`q1/main.py`、`q1/controller.py`、`q1/magnet.py` 和离线测试（A）。
- 适用边界：启用真上电不等于预先证明吸取成功；在视觉证据产生前写 `physical_pick_verified=true` 会伪造实机结果，因此仍由运行闭环更新。

## D-028 严格运动闭环：新鲜反馈门禁与硬故障

- 决策：部署 SDK `nexarm_sdk.py` 增加 `flush_input_buffer`、请求/响应时间戳与丢弃字节诊断；`get_current_coords` 默认先清缓冲再请求。禁止把命令前积压的 `CMD_GET_CUR_COORDS` 帧当作本次查询结果。
- 决策：正式执行器统一 `MotionAttempt`：记录 `COMMAND_SENT`、反馈元数据、样本、缓冲清理、时长与判定。大行程命令必须在完整 `duration_ms` 后出现可关联的新鲜反馈变化并稳定到位；否则 `STALE_FEEDBACK_HARDWARE_FAULT` / 超时硬故障，禁止下一位姿，磁铁保持关闭。
- 决策：删除 `real_arm_motion` / 把遥测等同物理事实的字段；成功路径也只写 `physical_evidence=UNPROVEN`，直至视觉等独立证据。
- 决策：删除 `q1.scripts.calibrate_single_pose`、`single_pose_calibration` 配置与对应单测；Jetson `q1_pose_calibration` 仅保留 `20260729_153642_988359`。
- 决策：覆盖 D-026 中“用户确认后 `direct_pick_release_pose_verified=true`”。在 flush 后新鲜反馈闭环实机证明前保持 `false`。
- 原因：F-022 已证明物理运动与陈旧遥测可并存；继续开环下一位姿或磁铁 ON 不可接受。
- 依据：F-022 `report.json`（A+D）；`hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py`、`q1/executors/nexarm.py`、`q1/controller.py`、`q1/config/robot_config.json`（A）。
- 当前状态：本地实现与单测落地；Jetson 无运动诊断与复位路径对齐已完成。F-023 表明当前负载下名义 HOME 未进入容差；正式抓放门禁保持关闭，直至 HOME 再次可重复到位且 fresh-feedback 闭环通过。

## D-029 将统一 HOME 调整为 (168,0,230,-88,1,1)

- 决策：用户明确停止继续修复旧 HOME，将统一 HOME/观察位由 `(173,4,226,-84.4,0,0)` 改为 `(168,0,230,-88,1,1)`；动作时长保持 6000 ms。
- 原因：用户希望提高观察位 Z，并将 Y 调到 0。旧 HOME 在断电重启、保留控制器加速度及确认软件/控制板限位均包含目标后，仍连续出现零坐标/舵机变化。相对稳定反馈 `(168,5,215,-88,1,1)` 约 ΔY=5 mm、ΔZ=15 mm，若执行链路仍不动作，将超过现有 10 mm 位置容差并继续超时。
- 依据：Jetson 运行 `20260729_164647_578613`、`20260729_170513_284352`；只读真实关节/TCP 报告 `output/diagnostics/nexarm_readonly/20260729_170214.json`（A）；用户 2026-07-30 明确决策（D）。
- 适用边界：这是项目回退，不证明旧 HOME 不可达，也不证明 AT32 到舵机的执行故障已经修复。`direct_pick_release_pose_verified` 与 `physical_pick_verified` 继续保持 `false`，不得据此解除抓放或电磁铁门禁。
- 当前状态：已写入本地统一配置和运行时默认值并同步 Jetson；JSON、语法、SHA256 与本地 18 项离线测试通过，尚未重新执行实机 HOME。

## D-030 Q1 改为单次观察、一次规划、顺序执行

- 决策：D-017/D-018/D-019/D-023/D-027 中“每片回 HOME、重新拍照、视觉审计、再规划下一片”的生产编排由本决策覆盖。正式主流程改为初始化相机/NexArm/STM32 → HOME/观察位 → 单次拍照识别和拼图求解 → 一次生成按 P1 到 P4 排序的 `PieceMove` 队列 → 顺序执行吸取、吸合、搬运和释放。
- 决策：生产运行只保存一张 `capture.png`；场景、完整队列、逐片执行和汇总分别写入结构化 JSON。删除每轮 `raw.png`、`scene.png`、`rectified.png`、`overlay.png`、debug 图片、重复审计/选择/重规划状态和 `--max-cycles`。
- 决策：这是上层编排收缩，不改变 `NexArmRobotExecutor` 的新鲜反馈、到位超时和后续位姿阻断，也不改变 `STM32MagnetController` 的状态确认、500 ms 租约和异常断电。`completed=true` 只表示队列执行完毕，不代表动作后视觉复核；运行中不再自动写 `physical_pick_verified=true`。
- 决策：完整生产入口使用 `production_run_blockers()`；该决策作出时 `direct_pick_release_pose_verified=false`，因此在任何相机或串口打开前拒绝启动。底层只读/HOME 诊断继续使用不含该生产门禁的设备初始化检查；当前值已由 D-033 更新。
- 原因：用户提供的 3.2.1 程序设计和流程图明确要求先完成一次视觉求解并生成 `PieceMove` 列表，再循环执行列表；现有逐片视觉闭环和多套图片后处理与该设计不一致，且增加现场理解和日志定位成本。
- 依据：用户 2026-07-30 提供的主程序设计与流程图（D）；`2026E/2026E副本/q1/pipeline.py::run_pipeline`、`motion.py::plan_motions`（历史源码，A）；`2026E/q1/controller.py::Q1Controller`、`motion.py::plan_piece_moves`、`state_machine.py::Q1State`（当前源码，A）。
- 当前状态：本地实现与 Mock/几何离线测试完成；未打开真实串口、未发送机械臂运动、未给电磁铁通电。V-013 与 D-028 的实机门禁继续有效。

## D-031 Q1 拆分为独立视觉规划和完整执行入口

- 决策：`q1.main` 提供 `plan` 与 `run` 两个阶段。`plan` 只允许打开 K230，单次拍照后生成 `capture.png`、`scene.json` 和 `piece_moves.json`；不构造 NexArm 或 STM32 控制器。`run` 才初始化三类设备、到 HOME 并执行完整队列。
- 决策：两个入口必须复用 `q1.workflow::capture_and_plan`，不得分别维护识别或规划实现。K230 Jetson 驱动的正式加载位置为 `2026E/drivers/k230_ttl_camera/jetson`。
- 决策：`plan` 使用独立令牌 `CAPTURE_AND_PLAN`。它不受 `direct_pick_release_pose_verified` 阻止，但仍要求纸面到机械臂映射、腕部方向和抓放高度字段齐全，确保输出的 `PieceMove` 是完整后续规划而不是只有像素坐标。
- 原因：当前 HOME/舵机执行故障和抓放精度尚未解决，但用户现阶段需要先在固定观察位验证完整 A4 构图、四片精确识别和后续动作规划；让生产抓放门禁同时阻止视觉开发会混淆两个独立问题。
- 依据：用户 2026-07-30 明确要求（D）；`q1/main.py`、`q1/workflow.py`、`q1/runtime_config.py::planning_blockers`、`q1/tests/test_q1_plan_entry.py`（A）；K230 `drivers/k230_ttl_camera/jetson/k230_camera.py` 与 `protocol.py`（A）。
- 当前状态：本地 `57 passed`、`compileall` 和 CLI 帮助检查通过；未连接 Jetson、未打开真实相机串口、未运动机械臂、未通电电磁铁。Jetson 实景结果见 V-014。

## D-032 删除 Q1 软件坐标范围并将抓放高度改为 Z15

- 决策：从正式规划、NexArm 执行器和 HOME 复位脚本中删除 XYZ/Pitch/Roll/Claw 软件范围检查；删除 `workspace_limits`、`wrist_roll_min_deg` 和 `wrist_roll_max_deg` 配置字段及对应拒绝分支，不以空范围或扩大范围替代。
- 决策：`pick_height` 与 `release_height` 同时由 25 改为 15。腕部仍使用零位和正负方向映射，角度不再受项目软件上下限拒绝。
- 依据：用户 2026-07-30 明确要求（D）；`q1/motion.py`、`q1/executors/nexarm.py`、`q1/scripts/test_camera_arm_reset.py`、`q1/calibration.py`、`q1/wrist.py` 和 `q1/config/robot_config.json`（A）。
- 适用边界：删除的是项目软件坐标范围，不改变板端固件限制、逆解结果或机械物理边界。本决策作出时 Z15 尚无实机验证且 `direct_pick_release_pose_verified=false`；该状态后来由 D-033 覆盖。
- 当前状态：仅本地代码和配置已修改；未连接 Jetson、未发送运动、未通电电磁铁。

## D-033 确认 Z15 完整吸取与释放位姿

- 决策：将正式配置 `direct_pick_release_pose_verified` 由 `false` 改为 `true`，保留 `pick_height=15` 和 `release_height=15`。
- 依据：用户于 2026-07-30 明确确认完整吸取与释放 XY/Z/Pitch/Roll 位姿均已到位（D）；`q1/config/robot_config.json` 与生产门禁测试（A）。
- 覆盖关系：本决策覆盖 D-032 中“Z15 尚无实机验证”的当前状态，不修改 D-023、D-026、D-028 中 Z25 和陈旧反馈的历史证据。
- 适用边界：位姿到位确认不等同于磁吸可靠性或最终拼放精度验证，`physical_pick_verified=false` 保持不变。
- 当前状态：本地配置和文档已更新；本次未连接 Jetson、未发送运动、未通电电磁铁。

## D-034 将统一 HOME 调整为 (180,0,200,-90,0,0)

- 决策：将 Q1 唯一 HOME/观察位由 D-029 的 `(168,0,230,-88,1,1)` 改为 `(180,0,200,-90,0,0)`；动作时间继续使用独立的 `move_duration_ms=6000`。
- 依据：用户于 2026-07-30 明确指定新 HOME（D）；`q1/config/robot_config.json`、`q1/main.py::_apply_robot_fields`（A）。
- 覆盖关系：本决策只覆盖 D-029 的当前 HOME 值，不删除此前 HOME 故障和反馈记录。
- 待实机验证：本次仅写入本地配置，未发送运动；配置值不能单独证明新 HOME 已到位。

## D-035 HOME 前不再写入全局加速度

- 决策：复位脚本和生产执行器在打开 NexArm 串口后只读取固件版本与当前位姿，第一条控制器写命令直接发送当前 HOME；删除 Q1 对 `CMD_SET_GLOBAL_ACC` 的调用、配置字段和命令行分支。
- 依据：用户于 2026-07-30 报告当前流程出现“先向下触地、再到 HOME”的实机现象并要求从开机位置直接到 HOME（D）；`q1/scripts/test_camera_arm_reset.py`、`q1/robot/safe_nexarm.py`、`q1/executors/nexarm.py` 与厂商 `system_task_handle.cpp::CMD_SET_GLOBAL_ACC`（A）。
- 覆盖关系：本决策覆盖 D-016 中生产初始化写入全局加速度 10 的当前要求；厂商 SDK 方法保留，但 Q1 不调用。
- 适用边界：主机端不存在 HOME 前的中间位姿命令。若单条 `CMD_COORDINATE_SET(HOME)` 仍产生下探轨迹，则该路径由控制板/舵机内部执行，不是 Python 发送了第二个位姿。
- 当前状态：仅完成本地实现和配置修改；Jetson 已断开，尚未上传或发送机械臂运动。

## D-036 将统一 HOME 调整为 (175,0,210,-90,0,0)

- 决策：将 Q1 唯一 HOME/观察位由 D-034 的 `(180,0,200,-90,0,0)` 改为 `(175,0,210,-90,0,0)`；动作时间继续使用独立的 `move_duration_ms=6000`。
- 依据：用户于 2026-07-30 根据现场取景明确指定该观察位，以使相机包含完整纸张（D）；`q1/config/robot_config.json`（A）。
- 覆盖关系：本决策只覆盖 D-034 的当前 HOME 值，不删除运行 `20260730_231532_316942` 的零运动故障证据。
- 待实机验证：当前只更新本地配置；新 HOME 的可达性、到位反馈和完整 A4 构图仍须分别实测。

## D-037 正式 Q1 按位姿动作时长推进并输出单张规划图

- 决策：正式 `q1.main run` 发送 HOME、吸取位和释放位后分别等待配置的 `move_duration_ms`，不再用当前陈旧的 NexArm 坐标/舵机反馈阻塞流程；HOME 时长结束后只拍一张正式图，输出 `capture.png`、`plan.png`、`scene.json`、`piece_moves.json`，随后立即执行完整队列。
- 依据：F-022、F-027 的物理运动与陈旧反馈证据；用户于 2026-07-30 明确要求单线完整流程并接受已验证位姿按动作时间执行（D）；`q1/controller.py::run`、`q1/executors/nexarm.py::_move_and_wait`、`q1/workflow.py::capture_and_plan`（A）。
- 覆盖关系：覆盖 D-026 中“无新鲜反馈变化时硬停”的生产路径决策；不修改 HOME、Z15、纸面映射、规划残差门限或 STM32 固件。
- 适用边界：`DURATION_ELAPSED` 只证明等待时间结束，不是控制器反馈到位证明；`physical_pick_verified=false` 继续表示磁吸和最终拼放结果尚未验证。
- 当前状态：本地实现和实图离线规划已通过；尚未执行修改后的真实机械臂/电磁铁流程。

## D-038 当前固定 Q1 四片目标统一放大 1.03

- 决策：保留赛题图 2 的 100×60 mm 原始模板，在 `robot_config.json` 为当前固定四片设置 `target_scale=1.03`；统一缩放全部目标顶点并将目标原点设为 `(53.5,191.85) mm`，使 103×61.8 mm 外框中心与 A4 下半区中心 `(105,222.75) mm` 重合，同时保持镜像方向和相邻关系不变。
- 依据：F-028 的实机图面积比例和刚体残差复算；用户于 2026-07-31 指出目标区域比例正确但整体略小（D）。
- 影响范围：只改变 Q1 当前四片的目标顶点、释放中心和规划图；不改变源轮廓识别、模板身份、HOME、Z15、纸面到机械臂映射或 STM32。
- 适用边界：该比例不得用于赛题第 2 项现场未知碎片；若更换自备碎片，也必须重新测量。
- 当前状态：仅本地修改并通过同一实图复算，未同步 Jetson、未发送运动、未通电电磁铁。

## D-042 Z-15 抓放之间使用三段斜向拱形搬运

- 决策：以 `transfer_apex_height=75` 为唯一新增搬运高度参数。吸取后依次发送 `25% XY/Z45/25% roll`、`60% XY/Z75/60% roll` 和 `100% XY/Z-15/100% roll` 三个位姿；每段 2000 ms，总时长保持 `move_duration_ms=6000`。
- 依据：F-032；厂商示例支持分段抬升、搬运和下降，但其纯 Z 航段不满足用户当前机械特性约束，因此改成每段同时改变平面位置和 Z 的拱形路径。
- 影响范围：只改变磁铁吸合后的 pick-to-release 搬运；HOME、吸取点、释放点、纸面映射和电磁铁租约不变。不恢复历史 Z226/Z250 航点，不发送全局加速度或分轴增量命令。
- 当前状态：本地四片离线规划和现有回归通过；未同步 Jetson，未执行新轨迹。

## D-041 NexArm 串口打开后立即用 3000 ms 发送 HOME

- 决策：正式 `q1.main run` 的启动顺序改为 `NexArm open → HOME(3000 ms) → 固件/坐标读取 → K230 初始化 → STM32 初始化 → 拍照规划`。HOME 下发并入 NexArm 初始化，控制器不再重复发送 HOME。
- 依据：F-031；用户于 2026-07-31 再次观察到启动后快速触地并要求直接到 HOME，同时认为原 6000 ms 复位过慢（D）。
- 影响范围：HOME 目标六维值保持 `(175,0,210,-90,0,0)`；仅 HOME 使用第七字段 `3000 ms`，P1–P4 吸取和释放继续使用独立的 `move_duration_ms=6000`。不写全局加速度、舵机参数或中间位姿。
- 覆盖关系：强化 D-035 的“HOME 为第一条控制写入”，从“握手读取后第一条控制写入”改为“串口打开后第一条协议写入”。
- 当前状态：本地实现和现有回归通过；未同步 Jetson，未发送真实运动或电磁铁命令。

## D-040 当前四角纸面到机械臂标定采用仿射最小二乘

- 决策：将横放图像四角先按 `vision.py` 的轴交换转换为标准纸面坐标，再使用四组用户实测机械臂 XY 拟合 3×3 仿射齐次矩阵；不使用可精确穿过四点但会引入非线性透视项的单应矩阵。
- 依据：F-030；相机透视已在像素到标准 A4 纸面的第一阶段消除，标准纸面到同一机械臂工作平面的关系采用仿射模型。四点不完全共仿射的偏差按测量误差最小二乘分摊。
- 影响范围：只更新 `q1/config/robot_config.json::paper_to_robot_matrix` 及对应现有回归断言；不改变 A4 检测、目标几何、HOME、Z、腕部或运动时序。
- 当前状态：本地图像识别、四片规划和现有回归通过；未同步 Jetson，未执行机械臂或电磁铁。

## D-039 横放 A4 优先使用左右半区和白色中线定框

- 决策：当前 Q1 固定构图中，满足“两个宽度接近的大暗区 + 中央窄亮线”时，该候选优先于单个最大黑框。上下边若被裁切，不把屏幕边缘直接当成完整 21 cm，而按已检测的 29.7 cm 长边与 A4 固定比例向画外恢复。
- 分界线门槛：Otsu 分割后的左右暗区只要求保留至少 `max(2 px, 0.2% 图宽)` 的有效间隔；白线是否可信仍由间隔亮像素比例、左右宽度比、中央位置和最大间隔共同判定。
- 依据：F-029；用户于 2026-07-31 明确 A4 固定横放、左侧为四片随机区、右侧为目标区、中央白线稳定可见，并要求不再调整 HOME（D）。
- 影响范围：只修改 `q1/vision.py::detect_paper` 的纸框候选；不改变 HOME、纸面到机械臂矩阵、碎片模板、目标比例、目标中心或运动控制。
- 适用边界：碎片不得被画面裁切；左右纸边和中央白线必须可见。该规则不扩展为任意残缺纸张推断。
- 当前状态：三张特殊样本全流程离线复算通过；未同步 Jetson。

## D-038 电磁铁控制板切换为 STM32F103VET6，控制脚改为 PC0

- 决策：当前电磁铁控制 MCU 由 STM32F103C8T6 切换为 STM32F103VET6；新固件工程为 `firmware/stm32f103ve_uart_magnet`，不覆盖旧 C8T6 工程。上层串口协议保持不变。USART1 仍用 PA9/PA10；MOSFET 控制脚由用户指定并确认的 PC0 取代旧 PB12，集中定义于 `board_config.h`。
- 原因：用户更换开发板；新板侧排针引出 PC0 供控制，不再假定 PB12。
- 依据：用户明确决策与 PC0 确认（D）；Keil 编译产物、CubeProgrammer 烧录 Verify、Windows PING 20/20、Jetson `MAGNET_ON 100` 自动关闭测试（A，见 F-028）。
- 覆盖关系：覆盖 D-004 中“当前板为 C8T6、控制脚 PB12”的现行状态；旧 C8T6/`PB12` 工程仅作历史保留。
- 适用边界：`STATUS MAGNET` 仍只表示固件 GPIO 锁存；工件吸取/释放与线圈电气额定值继续独立验证。
- 当前状态：阶段 A/B 已烧录并完成 Jetson 100ms 吸合与自动关闭测试。
