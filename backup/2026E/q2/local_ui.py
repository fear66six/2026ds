"""第二问本地交互：系统文件对话框选图"""

from __future__ import annotations

from pathlib import Path
from tkinter import Tk, filedialog


def pick_image_path(initial_dir: str | Path | None = None) -> str | None:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        kwargs = {
            "title": "选择拼图图片（A4 黑底，碎片在上半区）",
            "filetypes": [
                ("图片", "*.png *.jpg *.jpeg *.bmp *.webp"),
                ("所有文件", "*.*"),
            ],
        }
        if initial_dir:
            kwargs["initialdir"] = str(initial_dir)
        path = filedialog.askopenfilename(**kwargs)
    finally:
        root.destroy()
    return path or None
