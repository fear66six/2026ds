# 硬件连接

> 证据标记：A=当前源码，B=真实日志，C=报告，D=本次用户实机观察，U=未确认。以下“当前最终接线”主要来自 D；接线前仍应对照实物丝印、万用表和厂商资料。

## 总体连接

```text
数据/控制：
Jetson USB
  └─ ATK-MO340P V2.0
       TXD ─────────────> PA10 / USART1_RX
       RXD <───────────── PA9  / USART1_TX
       GND ────────────── STM32 GND ───── MOSFET control GND
       5V  ────────────── STM32 5V        [D；供电能力仍需确认]

负载供电：
7.4 V 电池 ─> 固定 5 V 降压模块 ─> MOSFET load supply ─> 5/6 V 电磁铁

控制：
STM32 PB12 ─> MOSFET PWM/IN
```

## Jetson、ATK 与 STM32

| 起点 | 终点 | 方向/用途 | 证据 |
|---|---|---|---|
| Jetson USB | ATK-MO340P USB | USB 串口适配器 | D |
| ATK TXD | STM32 PA10 / USART1_RX | ATK 发、STM32 收 | A+D |
| ATK RXD | STM32 PA9 / USART1_TX | STM32 发、ATK 收 | A+D |
| ATK GND | STM32 GND | 串口参考地 | D |
| ATK 5V | STM32 5V | 当前用户描述的供电路径 | D/U |

固件把 PA9 配置为 USART1_TX 推挽复用输出、PA10 配置为 USART1_RX 浮空输入，见 [`main.c`](../../../firmware/stm32f103_uart_magnet/src/main.c#L49)。串口逻辑电平必须兼容 STM32 的 3.3 V I/O；“ATK 5V 电源脚”不等于“串口信号为 5 V”。

当前固件不使用 PA11/PA12 实现 USB CDC。STM32 Micro-USB 可以有供电/物理连线作用，但不是本协议的正式通信通道。若 ATK 5V 已给 STM32 供电，不得再未经验证并接其他 5 V 电源，以免回灌。

**未确认项：** 本地项目资料尚未给出 ATK-MO340P 5V 输出的允许电流、来源和防回灌特性，不能仅凭本次描述认定其适合作为最终 STM32 电源。正式接线前应查模块手册或实测。

## STM32 与 MOSFET

| 起点 | 终点 | 逻辑 | 证据 |
|---|---|---|---|
| STM32 PB12 | MOSFET PWM/IN | 高电平开启、低电平关闭 | A（固件）+D（模块观察） |
| STM32 GND | MOSFET control GND | 必须共地 | D/工程要求 |

固件在系统时钟配置前即把 PB12 预装载并驱动为低，随后配置为 2 MHz 推挽输出；主程序初始化也再次执行安全低电平，见 [`system_stm32f10x.c`](../../../firmware/stm32f103_uart_magnet/src/system_stm32f10x.c#L180) 和 [`magnet_control.c`](../../../firmware/stm32f103_uart_magnet/src/magnet_control.c#L11)。

建议在 PB12/MOSFET 输入处增加约 10 kΩ 下拉，属于工程建议，不代表当前硬件已经安装。实际 MOSFET 模块的 `PWM/IN`、电源端和负载端定义必须以其丝印和原始资料为准。

## 电池、降压与电磁铁

| 起点 | 终点 | 要求 | 证据 |
|---|---|---|---|
| 7.4 V 电池 | 降压模块输入 | 极性正确；建议串联合适保险丝 | D/工程建议 |
| 降压模块固定 5 V 输出 | MOSFET 负载电源 | 接负载侧，不接 ATK | D |
| MOSFET 负载输出 | 5/6 V 电磁铁 | 端子定义按实物资料 | D/U |

- 若该 7.4 V 电池为常见 2S 锂电池，满电电压可能为 8.4 V；电池化学体系尚未在项目资料中确认。
- 不得把未经降压的电池直接接到额定 5/6 V 的负载。
- ATK 的 5V 只能考虑 STM32 低功耗供电，绝不能给电磁铁负载供电。
- 电磁铁为感性负载，必须确认 MOSFET 模块具有正确极性和额定能力的续流/浪涌保护。项目资料尚不足以证明当前模块的具体保护拓扑。
- STM32 GPIO 只能驱动 MOSFET 控制输入，不能直接驱动电磁铁。

## 上电前检查

1. 断开负载电源，核对 TX/RX 交叉与所有控制侧共地。
2. 确认 BOOT0=0、BOOT1=0，并确认只有一个 STM32 5 V 供电来源。
3. 核对降压输出确为目标电压、极性正确，再连接 MOSFET 负载侧。
4. 确认续流保护、端子压接、导线载流能力和保险丝。
5. 首次联调只执行 `MAGNET_OFF`、`PING`、`GET_STATUS`；负载测试需另行授权和现场监护。
