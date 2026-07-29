# STM32 USART1 文本协议

协议事实来自当前固件 [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c) 和 [`magnet_control.c`](../../../firmware/stm32f103_uart_magnet/src/magnet_control.c)，而不是旧设计稿。

## 传输格式

- USART1：115200 baud、8 data bits、no parity、1 stop bit、no flow control。
- PA9=TX，PA10=RX。
- ASCII 文本，一行一条命令；LF (`\n`) 结束，CR (`\r`) 被忽略，因此兼容 CRLF。
- 空行被忽略。
- 命令区 64 bytes，最多接收 63 个非 CR/LF 字符；更长行进入丢弃状态，直到下一 LF。
- RX 环形区为 128 bytes，实际最多容纳 127 个尚未处理的字节。

## 命令表

| 命令 | 参数 | 正常回复 | 错误回复 | 输出变化 | 幂等 | 自动关闭 | 验证 |
|---|---|---|---|---|---|---|---|
| `PING` | 无 | `PONG` | 无专用错误 | 否 | 是 | 不适用 | B：10/10 |
| `GET_STATUS` | 无 | `STATUS MAGNET=<0|1> FAULT=<0|1>` | 无专用错误 | 通常否；若软件状态与 PB12 ODR 不一致会强制关闭 | 是（安全不一致时会关闭） | 不适用 | B：`0/0` |
| `MAGNET_ON <duration_ms>` | 十进制整数，单位 ms，50–500 | `OK ON TIMEOUT_MS=<duration>` | `ERR invalid_timeout` | 合法时置高；非法时强制置低 | **否**；重复调用会重设截止时间 | 是 | A；D：用户报告实机成功，无日志 |
| `MAGNET_OFF` | 无 | `OK OFF` | 无专用错误 | 立即置低并清 `FAULT` | 是 | 不适用 | B |
| `EMERGENCY_OFF` | 无 | `OK OFF` | 无专用错误 | 立即置低并清 `FAULT` | 是 | 不适用 | A；D：用户报告验证，无日志 |

对应位置：

- 参数解析与 50–500 ms 限制：[`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L117)、[`magnet_control.h`](../../../firmware/stm32f103_uart_magnet/inc/magnet_control.h#L6)
- 命令分派：[`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L158)
- PB12 开关、状态与自动超时：[`magnet_control.c`](../../../firmware/stm32f103_uart_magnet/src/magnet_control.c#L24)

## 错误行为

固件只有以下实际错误文本，不应扩充未实现的错误码：

| 回复 | 触发条件 | PB12 | `FAULT` |
|---|---|---|---|
| `ERR invalid_timeout` | 缺参数、非十进制、溢出、`<50` 或 `>500` | 强制低 | 不主动置 1 |
| `ERR unknown_command` | 未知命令或命令格式不完全匹配 | 强制低 | 不主动置 1 |
| `ERR rx_overflow` | RX 环形区满，或 USART ORE/NE/FE/PE | 强制低 | 置 1 |
| `ERR line_too_long` | 一行超过 63 字符并遇到 LF | 超长时立即强制低；LF 后回复 | 置 1 |

`FAULT` 不是保留字段。当前它反映“本次启动后发生过 RX/UART 溢出类错误或超长行”，直到收到 `MAGNET_OFF` 或 `EMERGENCY_OFF` 才清零。未知命令和非法时间不会把 `FAULT` 置 1。

旧需求曾写“未知命令不得改变 PB12”，但当前源码的统一 `command_error()` 会调用 `magnet_force_off()`；以当前源码行为为准。

## `MAGNET` 字段含义

`magnet_get_state()` 比较软件变量与 PB12 的 ODR 锁存位；若两者不一致，会强制关闭并返回 0。它不测量 MOSFET 栅极、线圈电压、电流、磁力或工件位置。因此：

```text
MAGNET=0  ≠  线圈电流一定为零  ≠  工件已经释放
MAGNET=1  ≠  电磁铁一定通电    ≠  工件一定吸住
```

## 开启时序

```text
Jetson:  MAGNET_ON 200\n
              │
STM32:        解析并校验 50..500
              │
              ├─ PB12 置高、记录 deadline
              └─ 回复 OK ON TIMEOUT_MS=200
                          │
                    SysTick 每 1 ms 检查
                          │ 到期
                          └─ PB12 强制置低

Jetson:  GET_STATUS\n
STM32:   STATUS MAGNET=0 FAULT=0\n
```

截止时间用无符号计数加法和有符号差值比较，能安全跨越 32-bit 毫秒计数回绕，见 [`magnet_control.c`](../../../firmware/stm32f103_uart_magnet/src/magnet_control.c#L57)。

## 接口限制

- 没有无限时长开启，也没有 `HOLD` 或租约 ID。
- 重发合法 `MAGNET_ON` 会延长到“本次接收时间 + duration”，但驱动没有原子续租/通信看门狗保证；不得把它等同于已实现的持续搬运方案。
- UART 错误统一映射为 `ERR rx_overflow`，无法从回复区分 ORE、NE、FE、PE。
- 没有电流、吸取或物理释放反馈。
