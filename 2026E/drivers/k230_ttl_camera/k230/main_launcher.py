# Boot diagnostic + production camera server.
# Emits BOOT_UART_OK on UART3@460800 before camera init.
# Restore: bash ~/k230_ttl_camera/restore_k230_main.sh

import sys
import time

from machine import UART, FPIOA


def _boot_uart_beacon():
    fp = FPIOA()
    fp.set_function(50, FPIOA.UART3_TXD, oe=1)
    fp.set_function(51, FPIOA.UART3_RXD, ie=1)
    u = UART(
        UART.UART3,
        baudrate=460800,
        bits=UART.EIGHTBITS,
        parity=UART.PARITY_NONE,
        stop=UART.STOPBITS_ONE,
    )
    u.write(b"BOOT_UART_OK\n")
    time.sleep_ms(200)
    return u


try:
    _boot_uart_beacon()
except Exception as e:
    # continue to camera path; Jetson may still see nothing
    pass

sys.path.insert(0, "/sdcard/experiments/k230_ttl_jpeg")
try:
    import k230_camera_server

    k230_camera_server.main()
except Exception as e:
    try:
        from machine import UART, FPIOA

        fp = FPIOA()
        fp.set_function(50, FPIOA.UART3_TXD, oe=1)
        fp.set_function(51, FPIOA.UART3_RXD, ie=1)
        u = UART(
            UART.UART3,
            baudrate=460800,
            bits=UART.EIGHTBITS,
            parity=UART.PARITY_NONE,
            stop=UART.STOPBITS_ONE,
        )
        u.write(("FATAL %s\n" % e).encode())
        time.sleep_ms(300)
    except Exception:
        pass
    raise
