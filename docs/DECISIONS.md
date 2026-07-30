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
- 当前状态：固件和离线驱动已实现并编译；尚未烧录或执行 PB12 实机输出测试。
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
