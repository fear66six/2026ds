import zipfile
from pathlib import Path

docs = Path(r"D:/diansai/2026/docs")


def dump_case_blocks(zpath, member, needles, after=80):
    with zipfile.ZipFile(zpath) as z:
        lines = z.read(member).decode("utf-8", errors="replace").splitlines()
    print("\n####", zpath.name, "!", member)
    for i, line in enumerate(lines):
        if any(n in line for n in needles):
            print(f"\n-- L{i+1} --")
            for j in range(i, min(len(lines), i + after)):
                print(f"{j+1:5d}|{lines[j]}")
                # stop at next case at same indent roughly
                if j > i and lines[j].lstrip().startswith("case ") and "CMD_" in lines[j]:
                    break


# Primary ESP32 app firmware
primary = next(docs.rglob("Nex_Arm.zip"))
dump_case_blocks(
    primary,
    "Nex_Arm/system_task_handle.cpp",
    [
        "case CMD_COORDINATE_SET",
        "case CMD_GET_CUR_COORDS",
        "case CMD_SET_GLOBAL_ACC",
        "update_pose_from_coordinate_set",
        "CMD_GET_CUR_COORDS",
        "g_get_pos",
    ],
    after=60,
)

# Demo sys firmware
for zpath in docs.rglob("Nex_Arm.zip"):
    if "03" in zpath.as_posix() or "示例" in str(zpath):
        with zipfile.ZipFile(zpath) as z:
            names = [n for n in z.namelist() if n.endswith("system_task_handle.cpp")]
            print("\nDEMO ZIP", zpath)
            print(names)
            if names:
                dump_case_blocks(
                    zpath,
                    names[0],
                    [
                        "case CMD_COORDINATE_SET",
                        "case CMD_GET_CUR_COORDS",
                        "case CMD_SET_GLOBAL_ACC",
                        "update_pose_from_coordinate_set",
                    ],
                    after=70,
                )
        break

# Arm side ESP-NOW
for zpath in docs.rglob("机械臂.zip"):
    print("ARM ZIP", zpath)
    with zipfile.ZipFile(zpath) as z:
        for n in z.namelist():
            if n.endswith("system_task_handle.cpp"):
                dump_case_blocks(
                    zpath,
                    n,
                    [
                        "case CMD_COORDINATE_SET",
                        "case CMD_GET_CUR_COORDS",
                        "case CMD_SET_GLOBAL_ACC",
                        "update_pose_from_coordinate_set",
                        "func_ctrl_callback",
                    ],
                    after=80,
                )

# Search AT32 source for coordinate handling - may be binary only
print("\n#### Searching AT32 / kinematics sources for payload parse")
for zpath in docs.rglob("*.zip"):
    try:
        zf = zipfile.ZipFile(zpath)
    except Exception:
        continue
    for n in zf.namelist():
        low = n.lower()
        if not low.endswith((".c", ".cpp", ".h")):
            continue
        data = zf.read(n)
        if b"CMD_COORDINATE_SET" in data and (
            b"i_pitch" in data or b"pitch * 10" in data or b"raw_pitch" in data or b"args[0]" in data
        ):
            text = data.decode("utf-8", errors="replace")
            if "case CMD_COORDINATE_SET" in text or "CMD_COORDINATE_SET" in text and "GET_LOW_BYTE" in text:
                print(zpath)
                print(" ", n)
