# 证据追溯

本目录使用独立于 `AGENTS.md` 厂商可信度的任务证据标记：

- **A**：当前源码直接证明
- **B**：真实运行日志直接证明
- **C**：报告/清单记录
- **D**：本次用户实机观察或当前接线陈述
- **U**：现有证据无法确认

同一结论可有多个等级；D 不升级为 B，除非补充可追溯日志、照片或测量记录。

| 结论 | 文件 | 代码/日志位置 | 等级 | 备注 |
|---|---|---|---|---|
| USART1 为 115200 8N1、无流控 | [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L49)；[`usart1_runtime_test.log`](../../../logs/stm32_uart_bootloader/usart1_runtime_test.log) | 源码 49–73；日志 2 | A+B | 运行期；Bootloader 的 8E1 不适用 |
| PA9=TX、PA10=RX | [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L57) | 57–69 | A | 当前固件配置 |
| PB12 控制输出，高开低关 | [`magnet_control.c`](../../../firmware/stm32f103_uart_magnet/src/magnet_control.c#L4) | 4、16、26、41 | A | 模块真实极性另有 D 观察 |
| PB12 在时钟配置前默认低 | [`system_stm32f10x.c`](../../../firmware/stm32f103_uart_magnet/src/system_stm32f10x.c#L180) | 180–195 | A | 随后应用初始化再次置低 |
| 命令为 LF 结尾并兼容 CRLF | [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L257) | 257–273 | A | CR 被忽略 |
| 命令集及回复格式 | [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L158) | 158–213 | A | 不含其他命令 |
| `MAGNET_ON` 范围 50–500 ms | [`magnet_control.h`](../../../firmware/stm32f103_uart_magnet/inc/magnet_control.h#L6)；[`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L117) | 6–7；117–148 | A | 纯十进制整数 |
| 到期自动关闭 | [`magnet_control.c`](../../../firmware/stm32f103_uart_magnet/src/magnet_control.c#L57) | 57–63 | A | SysTick 入口见 main.c 20–25 |
| `STATUS MAGNET=x FAULT=y` | [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L169) | 169–175 | A | `MAGNET` 非物理传感 |
| `FAULT` 对 overflow/UART/长行生效 | [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L27) | 27–46、245–267 | A | 不是保留字段 |
| `MAGNET_OFF -> OK OFF` | [`usart1_runtime_test.log`](../../../logs/stm32_uart_bootloader/usart1_runtime_test.log) | 3–4 | B | COM15 实测 |
| `PING` 10/10 返回 `PONG` | 同上 | 5–24 | B | 真实运行日志 |
| `GET_STATUS -> MAGNET=0 FAULT=0` | 同上 | 25–26 | B | 只证明控制状态 |
| 该次真实日志未发送 `MAGNET_ON` | [`USART1_TEST_REPORT.md`](../../../logs/stm32_uart_bootloader/USART1_TEST_REPORT.md) | 21–22 | C | 当时负载断开 |
| `MAGNET_ON 50/100/500` 被接收并超时恢复 | 本次用户陈述 | 当前请求“已经验证的事实” | D | 项目内未找到对应原始串口日志 |
| MOSFET 指示灯按时亮灭、实物吸合成功 | 本次用户陈述 | 当前请求 | D | 无测量/视频/日志 |
| 电磁铁通过垫片和侧移可以释放 | 本次用户陈述 | 当前请求 | D | 等待、位移、材料需复标 |
| Jetson 曾用稳定 `by-id` 路径 | 本次用户陈述 | 当前请求 | D | 当前项目没有 Jetson 枚举日志 |
| `preferred_linux_port()` 支持单一 by-id 条目 | [`stm32_magnet_uart.py`](../../../drivers/stm32_magnet_uart.py#L198) | 198–203 | A | 不按 VID/PID/序列号筛选 |
| 驱动打开后先发送 `MAGNET_OFF` | [`stm32_magnet_uart.py`](../../../drivers/stm32_magnet_uart.py#L119) | 119–130 | A | 异常时关闭 |
| 驱动支持上下文和 Mock | [`stm32_magnet_uart.py`](../../../drivers/stm32_magnet_uart.py#L68) | 68–105、188–195 | A | Mock 不模拟真实超时 |
| 固件 Device ID 0x410、Flash 64 KiB、Bootloader 2.2 | [`UART_BOOTLOADER_REPORT.md`](../../../logs/stm32_uart_bootloader/UART_BOOTLOADER_REPORT.md) | 5–15 | C | Revision 未返回 |
| CubeProgrammer Verify 成功 | [`FLASHING_REPORT.md`](../../../logs/stm32_uart_bootloader/FLASHING_REPORT.md) | 30–39 | C | 仅擦除页 0–3 |
| 独立回读与构建 BIN 一致 | 同上 | 41–49 | C | 3648 bytes，SHA256 相同 |
| Option Bytes/RDP 未修改 | 同上 | 51–56 | C | 烧录步骤未 Go/Start |
| 原始 Flash 已备份并校验 | [`backup_manifest.json`](../../../backup/stm32_before_uart_magnet/backup_manifest.json) | 10–27 | C | 65536 bytes，size/SHA256 verified |
| 当前 STM32 精确板卡变体 | [`TODO_VERIFY.md`](../../TODO_VERIFY.md) | V-001/F-005 相关记录 | U | 资料含多个 F103C8T6 板型 |
| 当前电磁铁精确型号与额定参数 | [`TODO_VERIFY.md`](../../TODO_VERIFY.md) | V-006 | U | 文件名 5V 与图片 DC12V 有冲突 |
| ATK 5V 可可靠给 STM32 供电 | 本次用户陈述 | 当前接线描述 | D/U | 缺 ATK 正式电源能力证据 |
| 当前 MOSFET 续流拓扑与保护额定值 | [`TODO_VERIFY.md`](../../TODO_VERIFY.md) | V-005/V-006 | U | 不能仅凭“可吸合”推断保护充分 |

## 已发现冲突

1. [`DECISIONS.md`](../../DECISIONS.md) 的 D-004 仍写“尚未烧录或执行 PB12 实机输出测试”，但 [`FLASHING_REPORT.md`](../../../logs/stm32_uart_bootloader/FLASHING_REPORT.md) 已记录烧录/回读；本次用户又报告输出和负载测试。旧状态已过期，不用于当前接口结论。
2. [`TODO_VERIFY.md`](../../TODO_VERIFY.md) V-005/V-006 仍把 MOSFET 极性与电磁铁型号/额定值列为未确认。本次观察可支持“该次组合表现为高开且能吸合”（D），但不能替代输入阈值、额定电流、线圈型号和保护拓扑的正式确认。
3. 早期 [`USART1_TEST_REPORT.md`](../../../logs/stm32_uart_bootloader/USART1_TEST_REPORT.md) 明确记录当时没有发送 `MAGNET_ON` 且负载断开；它与之后用户口述的负载验证属于不同阶段，不构成日志证实。
4. 旧需求“未知命令不得改变 PB12”与当前源码冲突；当前 `command_error()` 会强制关闭，以源码为准。
5. 本次用户称 Jetson Orin Nano；全局 `TODO_VERIFY.md` 仍认为精确模块/载板未确认。接口文档只把本次称谓作为 D，不扩展到载板/SUPER 结论。
