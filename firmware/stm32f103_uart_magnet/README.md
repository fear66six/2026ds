# STM32F103C8T6 USART1 magnet controller

Independent Keil MDK project for the STM32F103C8T6 Micro-USB core board.

## Target

- HSE: 8 MHz, confirmed visually in the board schematic
- SYSCLK: 72 MHz
- Flash/RAM limits: 64 KiB / 20 KiB
- USART1: PA9 TX, PA10 RX, 115200 8N1
- control output: PB12 push-pull, active-high by project decision
- safe state: PB12 low
- USB CDC: not used

The MOSFET and electromagnet must remain disconnected until the separate no-load
verification steps are completed. The active-high assumption is not treated as a
vendor fact; confirm it on the actual MOSFET module before connecting a load.

## Build

The project is `firmware.uvprojx`. It was built with:

`D:\ti\Keil_v5\UV4\UV4.exe -b firmware.uvprojx -j0 -o build\build.log`

Build artifacts and hashes are in `build/`. Building does not access hardware.
Do not flash until the user provides the exact approval phrase required by the
project procedure.

## Source basis

- board schematic:
  `docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板硬件资料/STM32F103C8T6-MICRO-原理图.pdf`,
  page 1
- STM32F103x8/B data sheet:
  `docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板文档资料/STM32F103x8B_DS_CH_V10.pdf`
- CMSIS/startup/system files copied from the matching PA5 board example under
  `docs/进口芯STM32F103C8T6焊针下/STM32F103C8T6核心板程序资料/`

