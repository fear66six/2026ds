# Flash backup restore guide

This directory contains a read-only backup of the 64 KiB internal Flash read from
`0x08000000` before any UART magnet-controller firmware was written.

Do not restore automatically. A restore is a destructive Flash write and requires
explicit user approval, the correct STM32 UART Bootloader state, a second check of
Chip ID `0x410`, and verification of the backup SHA256.

Expected file:

- `flash_backup.bin`
- size: 65,536 bytes
- SHA256: `9CA0BBC9CB5998E0D352B0F92B7B03D32E4B22AAE415C8BC64DD208BBA1A3650`
- destination start address if restoration is explicitly approved: `0x08000000`

Before any restore:

1. Recompute the SHA256 and compare it with `backup_sha256.txt`.
2. Confirm BOOT0=1 and BOOT1=0, then reset or power-cycle the board.
3. Connect with 115200, 8E1 and verify Chip ID `0x410`.
4. Confirm the board is the same STM32F103C8T6 target and the Flash-size register
   at `0x1FFFF7E0` still reports `0x0040`.
5. Keep MOSFET, electromagnet, and load power disconnected.
6. Obtain explicit approval before constructing or executing any write command.

No restore command is included here to prevent accidental execution.
