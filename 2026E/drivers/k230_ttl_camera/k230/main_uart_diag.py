# TEMPORARY UART-only diagnostic main.py (no camera).
# After wiring verified, replace with production launcher via deploy_to_sd.sh

from machine import UART, FPIOA
import time

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
buf = b""
while True:
    c = u.read()
    if c:
        buf += c
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            t = line.decode("ascii", "ignore").strip()
            if t.startswith("PING"):
                rid = t.split()[1] if len(t.split()) > 1 else "?"
                u.write(("PONG %s\n" % rid).encode())
            elif t.startswith("STATUS"):
                rid = t.split()[1] if len(t.split()) > 1 else "?"
                u.write(("STATUS_OK %s session=1 frame=0 width=1280 height=720 q=65\n" % rid).encode())
    else:
        time.sleep_ms(2)
