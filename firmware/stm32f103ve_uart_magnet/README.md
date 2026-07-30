# STM32F103VET6 USART magnet / ping firmware

Independent Keil MDK projects ported from `firmware/stm32f103_uart_magnet`
(STM32F103C8T6). The C8T6 tree is left unchanged.

## Targets

| Project | Output | Purpose |
|---|---|---|
| `ping.uvprojx` | `build/stm32f103ve_uart_ping.*` | Stage A: USART + `PING`/`PONG` only |
| `magnet.uvprojx` | `build/stm32f103ve_uart_magnet.*` | Stage B: full magnet protocol |

## MCU / memory

- MCU: STM32F103VET6 (high-density, `STM32F10X_HD`)
- Startup: `startup/startup_stm32f10x_hd.s`
- Scatter: `firmware.sct` — Flash `0x08000000` / 512 KiB, SRAM `0x20000000` / 64 KiB
- Clock: HSE 8 MHz → SYSCLK 72 MHz (`system_stm32f10x.c`)

## Pins (provisional until board schematic confirmed)

See `inc/board_config.h`:

- USART1: PA9 TX, PA10 RX, 115200 8N1
- Magnet MOSFET drive: PB12 active-high (Stage B only)

`BOARD_UART_CONFIRMED` and `BOARD_MAGNET_GPIO_CONFIRMED` are currently `0`.

## Protocol (Stage B)

Same as C8T6 / `PROTOCOL.md`:

- `PING` → `PONG`
- `GET_STATUS` → `STATUS MAGNET=<0|1> FAULT=<0|1>`
- `MAGNET_ON <50..500>` → timed ON
- `MAGNET_OFF` / `EMERGENCY_OFF` → immediate OFF

Stage A rejects every non-`PING` command with `ERR unknown_command` and never
touches magnet GPIO.

## Build

```text
D:\ti\Keil_v5\UV4\UV4.exe -b ping.uvprojx -j0 -o build\ping_build.log
D:\ti\Keil_v5\UV4\UV4.exe -b magnet.uvprojx -j0 -o build\magnet_build.log
```

## Flash

Use ATK-MO340P USART bootloader after `BOOTLOADER_READY`. Do not flash Stage B
until Stage A PING 20/20 succeeds and magnet GPIO is confirmed.
