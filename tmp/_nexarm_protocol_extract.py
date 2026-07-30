import zipfile
from pathlib import Path

patterns = [
    "CMD_COORDINATE_SET",
    "CMD_GET_CUR_COORDS",
    "CMD_SET_GLOBAL_ACC",
    "update_pose_from_coordinate",
    "GLOBAL_ACC",
    "g_get_pos",
    "set_global",
    "espnow_set_global",
    "get_current_coords",
    "coordinate_set",
]


def dump_hits(label, text, window=30):
    lines = text.splitlines()
    print("\n====", label, "lines", len(lines), "====")
    seen = set()
    for i, line in enumerate(lines):
        if any(p in line for p in patterns):
            start = max(0, i - 3)
            end = min(len(lines), i + window)
            key = (start, end)
            if key in seen:
                continue
            seen.add(key)
            print(f"--- hit L{i+1}: {line.strip()[:140]} ---")
            for j in range(start, end):
                print(f"{j+1:5d}|{lines[j]}")
            print()


def main():
    docs = Path(r"D:/diansai/2026/docs")
    primary = next(docs.rglob("Nex_Arm.zip"))
    print("PRIMARY", primary)
    with zipfile.ZipFile(primary) as z:
        for n in z.namelist():
            if n.endswith((".cpp", ".h", ".c", ".py", ".ino", ".md")):
                print(" ", n)
        members = [
            "Nex_Arm/Global.h",
            "Nex_Arm/system_task_handle.cpp",
            "Nex_Arm/Robot_Arm.cpp",
            "Nex_Arm/CommProtocol.cpp",
            "Nex_Arm/ros_robot_controller_sdk.py",
        ]
        for m in members:
            text = z.read(m).decode("utf-8", errors="replace")
            if m.endswith("Global.h"):
                print("\n==== Global.h CMD subset ====")
                for line in text.splitlines():
                    if any(
                        k in line
                        for k in (
                            "CMD_COORDINATE",
                            "CMD_GET_CUR",
                            "CMD_SET_GLOBAL",
                            "CMD_ARM_MOVE",
                            "CMD_FIRMWARE",
                            "CMD_SET_TORQUE",
                            "CMD_SET_MOVE",
                        )
                    ):
                        print(line)
            else:
                dump_hits(f"{primary.name}!/{m}", text)

    uart = next(docs.rglob("UART_Control.zip"))
    print("\nUART", uart)
    with zipfile.ZipFile(uart) as z:
        for n in z.namelist():
            print(" ", n)
            if n.endswith(".py"):
                text = z.read(n).decode("utf-8", errors="replace")
                dump_hits(f"UART!/{n}", text, window=20)

    # AT32 firmware references and motion kinematics zip
    for zpath in docs.rglob("*.zip"):
        name = zpath.name.lower()
        if "at32" in name or "bus" in name:
            continue
    # Search inside primary zip for AT32 binary/header comments
    with zipfile.ZipFile(primary) as z:
        for m in ["Nex_Arm/at32_firmware.h", "Nex_Arm/AT32_OTA.md"]:
            text = z.read(m).decode("utf-8", errors="replace")
            print("\n====", m, "head ====")
            print("\n".join(text.splitlines()[:40]))


if __name__ == "__main__":
    main()
