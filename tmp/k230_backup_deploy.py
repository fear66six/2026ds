#!/usr/bin/env python3
"""Backup K230 sdcard root via gphoto2/MTP mount; deploy experiment scripts.

Does NOT modify main.py/boot.py. Only creates /experiments/k230_ttl_jpeg/.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

MTP_URI = "gphoto2://Kendryte_CanMV_001000000/"
SD_CANDIDATES = [
    "/run/user/1000/gvfs/gphoto2:host=Kendryte_CanMV_001000000/store_ffff0001",
    "/run/user/1000/gvfs/gphoto2:host=Kendryte_CanMV_001000000/",
]
IMPORTANT = ["main.py", "revision.txt", "game_vision.py", "suite_ui.py", "boot.py"]
LOCAL_SRC = Path.home() / "k230_ttl_jpeg_probe" / "k230_payload"
BACKUP_DIR = Path.home() / "k230_ttl_jpeg_probe" / "backups" / "k230_before"
REPORT = Path.home() / "k230_ttl_jpeg_probe" / "logs"


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.call(cmd)


def find_sd() -> Path | None:
    for p in SD_CANDIDATES:
        path = Path(p)
        if path.exists():
            # prefer store path if it has main.py
            if (path / "main.py").exists() or any(path.iterdir()):
                return path
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def list_tree(root: Path, out_list: Path, out_sha: Path, max_depth: int = 2) -> None:
    lines = []
    sha_lines = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        depth = 0 if str(rel) == "." else len(rel.parts)
        if depth > max_depth:
            dirnames[:] = []
            continue
        # skip huge trees
        dirnames[:] = [d for d in dirnames if d not in {".git", "__pycache__"}]
        for name in sorted(dirnames):
            p = Path(dirpath) / name
            try:
                st = p.stat()
                lines.append(f"DIR\t{p.relative_to(root)}\t{st.st_size}\t{st.st_mtime}")
            except Exception as e:
                lines.append(f"DIR\t{p.relative_to(root)}\tERR\t{e}")
        for name in sorted(filenames):
            p = Path(dirpath) / name
            try:
                st = p.stat()
                rel_s = str(p.relative_to(root)).replace("\\", "/")
                lines.append(f"FILE\t{rel_s}\t{st.st_size}\t{st.st_mtime}")
                if depth <= 1 or name in IMPORTANT or rel_s.startswith("experiments/"):
                    try:
                        sha_lines.append(f"{sha256_file(p)}  {rel_s}")
                    except Exception as e:
                        sha_lines.append(f"ERR:{e}  {rel_s}")
            except Exception as e:
                lines.append(f"FILE\t?\tERR\t{e}")
    out_list.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out_sha.write_text("\n".join(sha_lines) + "\n", encoding="utf-8")


def main() -> int:
    REPORT.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ensure MTP mounted
    run(["gio", "mount", "-u", MTP_URI])
    time.sleep(0.5)
    run(["timeout", "30", "gio", "mount", MTP_URI])
    time.sleep(1.0)
    sd = find_sd()
    if sd is None:
        # try listing gvfs
        gvfs = Path("/run/user/1000/gvfs")
        print("gvfs:", list(gvfs.iterdir()) if gvfs.exists() else None)
        print("ERROR: K230 sdcard MTP path not found", file=sys.stderr)
        return 2
    print("SD=", sd, flush=True)

    before_list = REPORT / "k230_sdcard_before.txt"
    before_sha = REPORT / "k230_sdcard_before_sha256.txt"
    list_tree(sd, before_list, before_sha, max_depth=2)
    print("wrote", before_list, before_sha, flush=True)

    for name in IMPORTANT:
        src = sd / name
        if src.exists() and src.is_file():
            dst = BACKUP_DIR / name
            shutil.copyfile(src, dst)
            print("backup", name, sha256_file(dst), flush=True)
        else:
            print("missing", name, flush=True)

    # deploy experiments
    exp = sd / "experiments" / "k230_ttl_jpeg"
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "temp").mkdir(parents=True, exist_ok=True)
    if not LOCAL_SRC.exists():
        print("ERROR: payload missing at", LOCAL_SRC, file=sys.stderr)
        return 3
    for p in LOCAL_SRC.iterdir():
        if p.is_file():
            dst = exp / p.name
            # MTP often rejects utime/copystat
            with open(p, "rb") as rf, open(dst, "wb") as wf:
                wf.write(rf.read())
            print("deploy", p.name, "->", dst, flush=True)

    # remove STOP if present
    stop = exp / "STOP"
    if stop.exists():
        stop.unlink()

    print("DEPLOY_OK", exp, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
