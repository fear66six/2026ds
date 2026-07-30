# STM32F103VET6 build and flash report

## MCU / linker

| Item | Value |
|---|---|
| Original project | `firmware/stm32f103_uart_magnet` (STM32F103C8T6, untouched) |
| New project | `firmware/stm32f103ve_uart_magnet` |
| Toolchain | Keil uVision + ARMCLANG V6.24 |
| MCU | STM32F103VE / `STM32F10X_HD` |
| Startup | `startup/startup_stm32f10x_hd.s` |
| Scatter | `firmware.sct` Flash `0x08000000+512KiB`, SRAM `0x20000000+64KiB` |
| Clock | HSE 8 MHz → SYSCLK 72 MHz |
| UART | USART1 PA9 TX / PA10 RX, 115200 8N1 (`BOARD_UART_CONFIRMED=1`) |
| Magnet GPIO | PC0 (`BOARD_MAGNET_GPIO_CONFIRMED=1`) |

## Stage A — ping

- Program Size: Code=2134 RO-data=410 RW-data=4 ZI-data=1172
- SHA256 hex: `2D33B5A36961FACEC572F010A50F845C317DFFD5A4F306DEA07B226C2F83DE04`
- Flash/verify: OK, chip ID `0x414`, High-density 512 KiB
- Application test: PING → PONG, 20/20 @ 115200 8N1 (Windows COM15)

## Stage B — magnet (PC0)

- Program Size: Code=3182 RO-data=522 RW-data=4 ZI-data=1180
- Map: LR_IROM1 base `0x08000000`, Max `0x00080000`; RW_IRAM1 base `0x20000000`, Max `0x00010000`
- SHA256 hex: `DBA53D5535D330401E74DDDEF9A9741F5AABC0807157E3F9CA519A2DEF20A381`
- SHA256 bin: `6D10159D389824B7F088C9EBE33BED16EBCD8155B186746245B502A925F27257`
- Flash/verify: OK on COM15
- Jetson by-id: `/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B7A030191-if00`
- Jetson results: PING True; STATUS MAGNET=0 FAULT=0; MAGNET_ON 100 OK; STATUS after 250 ms MAGNET=0 FAULT=0; MAGNET_OFF OK; EMERGENCY_OFF OK

## Re-flash command

```text
"C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe" -c port=COM15 br=115200 P=EVEN db=8 sb=1 fc=OFF -d "D:\diansai\2026\firmware\stm32f103ve_uart_magnet\build\stm32f103ve_uart_magnet.hex" -v
```

Require BOOTLOADER_READY before erase/write. Re-check ATK COM number each time.
