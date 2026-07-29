# Static safety report

Result: pass for the requested pre-flash checks.

| Check | Result | Evidence |
|---|---|---|
| PB12 is made safe early | Pass | `SystemInit` enables GPIOB, writes BRR, configures PB12 push-pull, then writes BRR again before clock setup |
| No transient software high during initialization | Pass | ODR is preloaded low before CRH mode change; no BSRR-high call occurs in initialization |
| PB12 defaults low after reset/application start | Pass | `SystemInit`, `magnet_gpio_init_safe`, and final pre-loop `magnet_force_off` |
| PA9/PA10 direction | Pass | PA9 AF push-pull TX; PA10 floating-input RX |
| USART1 runtime format | Pass | BRR from 72 MHz/115200; CR2=0, CR3=0, CR1 has UE/TE/RE/RXNEIE: 115200 8N1, no flow control |
| USB CDC absent | Pass | no USB peripheral initialization or USB source file in project |
| Timed-on required | Pass | only exact `MAGNET_ON ` prefix plus strict 50-500 decimal parser calls `magnet_turn_on_timed` |
| Timeout always forces off | Pass | `SysTick_Handler` calls `magnet_tick_isr`; wrap-safe signed subtraction calls `magnet_force_off` |
| Unknown/invalid command safety | Pass | `command_error` calls `magnet_force_off` before replying |
| Receive bounds | Pass | 128-byte single-producer/single-consumer ring and 64-byte bounded command buffer |
| UART receive errors | Pass | ORE/NE/FE/PE discard input and raise fail-safe overflow handling |
| ISR shared state | Pass | shared ring indexes, flags, ticks, state, and deadline are volatile; 32-bit accesses are aligned/atomic on Cortex-M3 |
| Tick wraparound | Pass | deadline comparison uses `(int32_t)(now - deadline) >= 0` |
| No auto-on test code | Pass | no startup, loop, LED, or periodic activation path |
| Flash/RAM limits | Pass | Keil: Code 3186, RO 454, RW 4, ZI 1180; target limits 64 KiB Flash / 20 KiB RAM |
| Compiler diagnostics | Pass | Keil Arm Compiler 6.24: 0 errors, 0 warnings |

Residual hardware verification:

- Confirm PB12 physical header position on the actual board.
- Confirm the connected MOSFET module is high-level-on and its input is
  compatible with 3.3 V logic.
- Perform only the documented no-load voltage test before any load connection.

