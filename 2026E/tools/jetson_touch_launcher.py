#!/usr/bin/env python3
"""Touch-friendly launcher for Q1/Q2/Q3 run on Jetson."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_ROBOT_CONFIG = PROJECT_ROOT / "q1" / "config" / "robot_config.json"
RUNTIME_CONFIG_PATH = Path("/tmp/2026e_touch_launcher_robot_config.json")

GAP_STEP_MM = 0.5
GAP_MIN_MM = 0.0
GAP_MAX_MM = 15.0

TASKS = {
    "q1": {
        "label": "Q1\n固定四片",
        "module": "q1.main",
        "run_confirm": "RUN_Q1",
    },
    "q2": {
        "label": "Q2\n随机四边形",
        "module": "q2.main",
        "run_confirm": "RUN_Q2",
    },
    "q3": {
        "label": "Q3\n扑克牌",
        "module": "q3.main",
        "run_confirm": "RUN_Q3",
    },
}

OUTPUT_PATTERNS = (
    re.compile(r"output=(.+)", re.IGNORECASE),
    re.compile(r"Q[123]_RUN_DIR=(.+)", re.IGNORECASE),
    re.compile(r"Q[123]_LAST_RUN_DIR=(.+)", re.IGNORECASE),
    re.compile(r"run=(.+)", re.IGNORECASE),
)


def load_base_robot_config() -> dict:
    if not BASE_ROBOT_CONFIG.exists():
        raise FileNotFoundError(f"robot config not found: {BASE_ROBOT_CONFIG}")
    return json.loads(BASE_ROBOT_CONFIG.read_text(encoding="utf-8"))


def default_edge_gap_mm() -> float:
    data = load_base_robot_config()
    return float(data.get("edge_gap_mm", 5.0))


def write_runtime_robot_config(
    edge_gap_enabled: bool,
    edge_gap_mm: float,
) -> Path:
    data = load_base_robot_config()
    data["edge_gap_enabled"] = bool(edge_gap_enabled)
    data["edge_gap_mm"] = round(float(edge_gap_mm), 1)
    RUNTIME_CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return RUNTIME_CONFIG_PATH


def parse_output_dir(text: str) -> Path | None:
    for line in text.splitlines():
        for pattern in OUTPUT_PATTERNS:
            match = pattern.search(line.strip())
            if match:
                candidate = Path(match.group(1).strip())
                if candidate.exists():
                    return candidate
    return None


class TouchLauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.edge_gap_enabled_var = tk.BooleanVar(value=True)
        self.edge_gap_mm_var = tk.DoubleVar(value=default_edge_gap_mm())
        self.gap_display_var = tk.StringVar(value="")
        self.worker: threading.Thread | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.task_buttons: dict[str, tk.Button] = {}
        self.gap_controls: list[tk.Widget] = []

        self.root.title("2026E 拼图可视化")
        self.root.geometry("1024x680")
        self.root.minsize(800, 560)
        self._configure_style()
        self._build_ui()
        self._refresh_gap_display()
        self.root.after(120, self._poll_events)

    def _configure_style(self) -> None:
        style = ttk.Style()
        for theme in ("clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break
        style.configure("Title.TLabel", font=("Sans", 24, "bold"))
        style.configure("Status.TLabel", font=("Sans", 14))
        style.configure("GapSection.TLabel", font=("Sans", 20, "bold"))
        style.configure("GapValue.TLabel", font=("Sans", 34, "bold"))

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        ttk.Label(outer, text="2026E 拼图可视化", style="Title.TLabel").pack(
            anchor=tk.W, pady=(0, 10)
        )

        task_frame = ttk.Frame(outer)
        task_frame.pack(fill=tk.X, pady=(0, 10))
        task_frame.columnconfigure(0, weight=1)
        task_frame.columnconfigure(1, weight=1)
        task_frame.columnconfigure(2, weight=1)

        for column, (key, meta) in enumerate(TASKS.items()):
            button = tk.Button(
                task_frame,
                text=meta["label"],
                font=("Sans", 28, "bold"),
                height=3,
                wraplength=220,
                command=lambda task_key=key: self._start_job(task_key),
            )
            button.grid(row=0, column=column, sticky="nsew", padx=8, ipady=18)
            self.task_buttons[key] = button

        gap_frame = ttk.LabelFrame(outer, text="拼缝 Gap 设置", padding=10)
        gap_frame.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(
            gap_frame,
            text="运行前可调整；下方实时显示当前值",
            style="GapSection.TLabel",
        ).pack(anchor=tk.W, pady=(0, 8))

        controls = ttk.Frame(gap_frame)
        controls.pack(fill=tk.X)
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=2)
        controls.columnconfigure(2, weight=1)

        minus_button = tk.Button(
            controls,
            text="−",
            font=("Sans", 36, "bold"),
            height=2,
            width=4,
            command=self._decrease_gap,
        )
        minus_button.grid(row=0, column=0, sticky="nsew", padx=(0, 8), ipady=10)

        value_frame = ttk.Frame(controls)
        value_frame.grid(row=0, column=1, sticky="nsew", padx=8)
        self.gap_value_label = ttk.Label(
            value_frame,
            textvariable=self.gap_display_var,
            style="GapValue.TLabel",
            anchor=tk.CENTER,
            justify=tk.CENTER,
        )
        self.gap_value_label.pack(fill=tk.BOTH, expand=True, pady=(0, 6))
        self.edge_gap_toggle_button = tk.Button(
            value_frame,
            text="",
            font=("Sans", 22, "bold"),
            height=1,
            command=self._toggle_edge_gap_enabled,
        )
        self.edge_gap_toggle_button.pack(fill=tk.X, ipady=8)

        plus_button = tk.Button(
            controls,
            text="+",
            font=("Sans", 36, "bold"),
            height=2,
            width=4,
            command=self._increase_gap,
        )
        plus_button.grid(row=0, column=2, sticky="nsew", padx=(8, 0), ipady=10)

        self.gap_controls.extend(
            [minus_button, plus_button, self.edge_gap_toggle_button]
        )

        self.status_var = tk.StringVar(value="就绪。点击上方题目按钮开始执行。")
        ttk.Label(outer, textvariable=self.status_var, style="Status.TLabel").pack(
            anchor=tk.W, pady=(0, 8)
        )

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=6)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.log_box = scrolledtext.ScrolledText(
            log_frame, font=("Monospace", 11), wrap=tk.WORD
        )
        self.log_box.pack(fill=tk.BOTH, expand=True)

    def _refresh_gap_display(self) -> None:
        enabled = self.edge_gap_enabled_var.get()
        gap_mm = float(self.edge_gap_mm_var.get())
        if enabled:
            self.gap_display_var.set(f"Gap: {gap_mm:.1f} mm")
            self.gap_value_label.configure(foreground="#0b6e4f")
            toggle_text = "Gap 已开启"
            toggle_bg = "#d9f2e6"
        else:
            self.gap_display_var.set(f"Gap: 关闭 ({gap_mm:.1f} mm)")
            self.gap_value_label.configure(foreground="#666666")
            toggle_text = "Gap 已关闭（点击开启）"
            toggle_bg = "#ececec"
        self.edge_gap_toggle_button.configure(
            text=toggle_text,
            bg=toggle_bg,
            activebackground=toggle_bg,
        )

    def _set_gap_mm(self, gap_mm: float) -> None:
        clamped = max(GAP_MIN_MM, min(GAP_MAX_MM, round(float(gap_mm), 1)))
        self.edge_gap_mm_var.set(clamped)
        self._refresh_gap_display()
        self._append_log(
            f"Gap 设置为 {clamped:.1f} mm"
            + ("（开启）" if self.edge_gap_enabled_var.get() else "（关闭，运行时不生效）")
        )

    def _decrease_gap(self) -> None:
        self._set_gap_mm(float(self.edge_gap_mm_var.get()) - GAP_STEP_MM)

    def _increase_gap(self) -> None:
        self._set_gap_mm(float(self.edge_gap_mm_var.get()) + GAP_STEP_MM)

    def _toggle_edge_gap_enabled(self) -> None:
        self.edge_gap_enabled_var.set(not self.edge_gap_enabled_var.get())
        self._refresh_gap_display()
        enabled = self.edge_gap_enabled_var.get()
        gap_mm = float(self.edge_gap_mm_var.get())
        self._append_log(
            f"Gap {'开启' if enabled else '关闭'} -> "
            f"{gap_mm:.1f} mm"
            + ("" if enabled else "（运行时不加 gap）")
        )

    def _set_busy(self, busy: bool) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        for button in self.task_buttons.values():
            button.configure(state=state)
        for widget in self.gap_controls:
            widget.configure(state=state)

    def _append_log(self, text: str) -> None:
        self.log_box.insert(tk.END, text.rstrip() + "\n")
        self.log_box.see(tk.END)

    def _start_job(self, task_key: str) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("忙碌", "当前已有任务在运行，请稍候。")
            return
        self._set_busy(True)
        enabled = self.edge_gap_enabled_var.get()
        gap_mm = float(self.edge_gap_mm_var.get())
        gap_summary = f"{gap_mm:.1f} mm" if enabled else "关闭"
        self.status_var.set(
            f"正在运行 {task_key.upper()}（Gap={gap_summary}）..."
        )
        self._append_log(f"=== START {task_key.upper()} RUN (Gap={gap_summary}) ===")
        self.worker = threading.Thread(
            target=self._run_job_thread,
            args=(task_key, enabled, gap_mm),
            daemon=True,
        )
        self.worker.start()

    def _run_job_thread(
        self,
        task_key: str,
        edge_gap_enabled: bool,
        edge_gap_mm: float,
    ) -> None:
        meta = TASKS[task_key]
        try:
            robot_config = write_runtime_robot_config(
                edge_gap_enabled,
                edge_gap_mm,
            )
            command = [
                sys.executable,
                "-m",
                meta["module"],
                "run",
                "--robot-config",
                str(robot_config),
                "--camera-backend",
                "k230_ttl",
                "--magnet-backend",
                "stm32",
                "--confirm",
                meta["run_confirm"],
            ]
            self.events.put(("log", "命令: " + " ".join(command)))
            completed = subprocess.run(
                command,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                env=os.environ.copy(),
            )
            output = (completed.stdout or "") + (
                "\n" + completed.stderr if completed.stderr else ""
            )
            self.events.put(("log", output.strip()))
            if completed.returncode != 0:
                self.events.put(
                    (
                        "error",
                        f"{task_key.upper()} run 失败，退出码 {completed.returncode}",
                    )
                )
                return
            output_dir = parse_output_dir(output)
            if output_dir is None:
                self.events.put(("error", "任务完成，但未找到输出目录。"))
                return
            self.events.put(("success", output_dir))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "error":
                self.status_var.set(str(payload))
                messagebox.showerror("运行失败", str(payload))
                self._set_busy(False)
            elif kind == "success":
                output_dir = Path(payload)
                self.status_var.set(f"完成：{output_dir}")
                self._append_log(f"输出目录: {output_dir}")
                self._set_busy(False)
        self.root.after(120, self._poll_events)


def main() -> int:
    if not PROJECT_ROOT.exists():
        messagebox.showerror("路径错误", f"未找到工程目录: {PROJECT_ROOT}")
        return 1
    root = tk.Tk()
    TouchLauncherApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
