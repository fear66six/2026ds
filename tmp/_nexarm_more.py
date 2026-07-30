import zipfile
from pathlib import Path

docs = Path(r"D:/diansai/2026/docs")
primary = next(docs.rglob("Nex_Arm.zip"))

needles = [
    b"g_get_pos",
    b"TIMING_EVENT_SERVO",
    b"update_status",
    b"CMD_GET_CUR_COORDS",
    b"handshake",
    b"MODE_",
    b"set_torque",
    b"sleep",
    b"enable_sync",
]

with zipfile.ZipFile(primary) as z:
    text = z.read("Nex_Arm/system_task_handle.cpp").decode("utf-8", errors="replace")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "g_get_pos" in line or "TIMING_EVENT_SERVO_STATUS" in line or "SERVO_STATUS_UPDATE" in line:
            for j in range(max(0, i - 5), min(len(lines), i + 25)):
                print(f"{j+1:5d}|{lines[j]}")
            print("---")

# Look for AT32 firmware source outside zip (binary blobs)
print("\nAT32 related files:")
for p in docs.rglob("*"):
    name = p.name.lower()
    if "at32" in name and p.is_file() and p.suffix.lower() in {".h", ".c", ".cpp", ".bin", ".hex", ".md"}:
        print(p)

with zipfile.ZipFile(primary) as z:
    for n in z.namelist():
        if "at32" in n.lower() or "firmware" in n.lower():
            info = z.getinfo(n)
            print(f"ZIP {n} size={info.file_size}")

# UART basic_demo sequence
uart = next(docs.rglob("UART_Control.zip"))
with zipfile.ZipFile(uart) as z:
    demo = z.read("basic_demo.py").decode("utf-8", errors="replace")
print("\n==== basic_demo.py ====")
print(demo)

# WiFi sdk set_pose for parity
wifi = next(docs.rglob("WiFi_Control.zip"))
with zipfile.ZipFile(wifi) as z:
    text = z.read("nexarm_wifi_sdk.py").decode("utf-8", errors="replace")
    for i, line in enumerate(text.splitlines()):
        if "def set_pose" in line or "def get_current" in line or "def set_global" in line or "pitch * 10" in line:
            for j in range(i, min(len(text.splitlines()), i + 40)):
                print(f"{j+1:5d}|{text.splitlines()[j]}")
            print("---")
