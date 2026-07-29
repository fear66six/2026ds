# USART1 protocol

Runtime serial settings are 115200 baud, 8 data bits, no parity, 1 stop bit, and
no flow control. This differs from the ROM Bootloader setting of 115200 8E1.

Commands are ASCII and terminate with LF. CR in CRLF is ignored.

| Command | Response | Effect |
|---|---|---|
| `PING` | `PONG` | none |
| `GET_STATUS` | `STATUS MAGNET=<0|1> FAULT=<0|1>` | none |
| `MAGNET_ON <ms>` | `OK ON TIMEOUT_MS=<ms>` | PB12 high for 50-500 ms |
| `MAGNET_OFF` | `OK OFF` | PB12 low immediately |
| `EMERGENCY_OFF` | `OK OFF` | PB12 low immediately |

Invalid, unknown, overlong, or receive-error input forces PB12 low and returns
`ERR <reason>`. A command line is limited to 63 characters. `MAGNET_ON` never
accepts a missing, signed, zero, nonnumeric, below-minimum, or above-maximum
duration.

