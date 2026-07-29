# STM32 UART firmware environment check

- Date: 2026-07-29
- Environment: native Windows PowerShell
- Workspace: `D:\diansai\2026`

| Tool | Version/status | Path |
|---|---|---|
| STM32CubeProgrammer GUI | 2.23.0 | `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32CubeProgrammer.exe` |
| STM32 Programmer CLI | 2.23.0 | `C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe` |
| Keil uVision | 5.43.1 | `D:\ti\Keil_v5\UV4\UV4.exe` |
| Arm Compiler for Embedded | 6.24 | `D:\ti\Keil_v5\ARM\ARMCLANG\bin\armclang.exe` |
| fromelf | 6.24 | `D:\ti\Keil_v5\ARM\ARMCLANG\bin\fromelf.exe` |
| STM32F1 DFP | installed pack directory absent; web catalog description present | `D:\ti\Keil_v5\ARM\PACK\.Web\Keil.STM32F1xx_DFP.pdsc` |

The project builds successfully without installing a pack because its matching
CMSIS device header, system source, and startup file are copied locally from the
project's original board example.

## COM15

- name: `USB-Enhanced-SERIAL CH343 (COM15)`
- PNPDeviceID: `USB\VID_1A86&PID_55D3\5B7A030191`
- VID/PID: `1A86:55D3`
- manufacturer: `wch.cn`
- service: `CH343SER_A64`
- driver: `2.2.2026.5`, `oem121.inf`
- status: `OK`

MobaXterm was running during the process scan, but COM15 opened exclusively and
successfully in CubeProgrammer, so it was not occupying this port. No process was
terminated.

