"""Q1 摄像头基准核心；只有显式调用 run_benchmark 才访问摄像头。"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
import shutil
import time
from typing import Optional

import cv2
import numpy as np

from . import config
from .camera_run import render_live_result
from .camera_source import (
    LatestFrameCamera,
    camera_properties,
    configure_camera,
    open_camera,
)
from .live_detect import LiveDetector


def _percentiles(values: list[float], points=(50, 95, 99)) -> dict:
    if not values:
        return {f"p{p}": None for p in points}
    array = np.asarray(values, dtype=np.float64)
    return {f"p{p}": float(np.percentile(array, p)) for p in points}


def _memory_rss_mb() -> Optional[float]:
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        )
        return counters.WorkingSetSize / 1048576.0 if ok else None
    status = Path("/proc/self/status")
    if status.exists():
        for line in status.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("VmRSS:"):
                return float(line.split()[1]) / 1024.0
    return None


def _linux_camera_and_thermal_info() -> dict:
    if not sys_platform_linux():
        return {"video_devices": [], "thermal_zones": [], "tegrastats": None}
    video_devices = sorted(str(path) for path in Path("/dev").glob("video*"))
    thermal = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        try:
            temp = float((zone / "temp").read_text().strip()) / 1000.0
            kind = (zone / "type").read_text().strip()
            thermal.append({"type": kind, "temperature_c": temp})
        except (OSError, ValueError):
            continue
    return {
        "video_devices": video_devices,
        "thermal_zones": thermal,
        "tegrastats": shutil.which("tegrastats"),
    }


def sys_platform_linux() -> bool:
    return platform.system().lower() == "linux"


def _write_reports(result: dict, report_dir: Path) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    label = platform.system().lower().replace(" ", "_")
    json_path = report_dir / f"q1_camera_benchmark_{label}.json"
    md_path = report_dir / f"q1_camera_benchmark_{label}.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md = [
        f"# Q1 camera benchmark: {label}",
        "",
        f"- mode: `{result['mode']}`",
        f"- frames: {result['frames_displayed_or_consumed']}",
        f"- OpenCV: `{result['opencv_version']}`",
        f"- backend: `{result['camera']['backend']}`",
        f"- requested: `{result['requested_width']}x{result['requested_height']} @ {result['requested_fps']}`",
        f"- actual: `{result['camera']['width']}x{result['camera']['height']} @ CAP_PROP_FPS={result['camera']['fps']}`",
        f"- FOURCC: `{result['camera']['fourcc']}`",
        f"- measured capture FPS: `{result['capture_fps']:.2f}`",
        f"- display FPS: `{result['display_fps']:.2f}`",
        f"- detect FPS: `{result['detect_fps']:.2f}`",
        f"- cap.read ms avg/P50/P95/P99: `{result['read_ms_average']:.2f}` / "
        f"`{result['read_ms_p50']:.2f}` / `{result['read_ms_p95']:.2f}` / "
        f"`{result['read_ms_p99']:.2f}`",
        f"- detect ms P50/P95: `{result['detect_ms_p50']}` / `{result['detect_ms_p95']}`",
        f"- possible skipped/latest-frame drops: `{result['possible_backlog_frames']}`",
        f"- failed reads: `{result['failed_reads']}`",
        f"- process CPU percent (one-core scale): `{result['process_cpu_percent']:.2f}`",
        f"- RSS MiB: `{result['memory_rss_mb']}`",
        "",
        "> CAP_PROP_FPS 仅为驱动报告值；验收应使用 measured capture/display FPS。",
    ]
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return json_path, md_path


def _probe_common_modes(cap, backend: str, requested: dict) -> list[dict]:
    """用真实读帧核验常见模式；GStreamer pipeline 本身为固定 caps，跳过重设。"""
    if backend.lower() == "gstreamer":
        return [{"note": "GStreamer mode is fixed by the selected pipeline caps"}]
    results = []
    for width, height, fps, fourcc in (
        (640, 480, 30.0, "MJPG"),
        (640, 480, 30.0, "YUYV"),
        (1280, 720, 30.0, "MJPG"),
        (1280, 720, 30.0, "YUYV"),
    ):
        configure_camera(
            cap,
            width=width,
            height=height,
            fps=fps,
            fourcc=fourcc,
            print_diagnostics=False,
        )
        started = time.perf_counter()
        ok, frame = cap.read()
        read_ms = (time.perf_counter() - started) * 1000.0
        actual = camera_properties(cap)
        results.append(
            {
                "requested": {
                    "width": width,
                    "height": height,
                    "fps": fps,
                    "fourcc": fourcc,
                },
                "actual": actual,
                "read_ok": bool(ok and frame is not None),
                "read_ms": read_ms,
            }
        )
    configure_camera(cap, print_diagnostics=False, **requested)
    return results


def run_benchmark(
    *,
    camera_index: int = 0,
    backend: str = "auto",
    width: int = config.CAMERA_WIDTH,
    height: int = config.CAMERA_HEIGHT,
    fps: float = config.CAMERA_FPS,
    fourcc: str = config.CAMERA_FOURCC,
    mode: str = "capture_only",
    frames: int = 300,
    report_dir: Optional[Path] = None,
) -> dict:
    if mode not in {"capture_only", "capture_display", "capture_display_detect"}:
        raise ValueError(f"unknown benchmark mode: {mode}")
    if frames < 300:
        raise ValueError("camera benchmark requires at least 300 frames")

    cap = open_camera(
        camera_index,
        backend=backend,
        width=width,
        height=height,
        fps=fps,
        fourcc=fourcc,
    )
    supported_mode_probe = _probe_common_modes(
        cap,
        backend,
        {"width": width, "height": height, "fps": fps, "fourcc": fourcc},
    )
    properties = camera_properties(cap)
    camera = LatestFrameCamera(cap).start()
    detector = (
        LiveDetector(config.DEFAULT_HSV_RANGES)
        if mode == "capture_display_detect"
        else None
    )
    display_enabled = mode != "capture_only"
    consumed = 0
    displayed = 0
    skipped = 0
    last_sequence: Optional[int] = None
    detect_samples = []
    last_processed = 0
    wall_start = time.perf_counter()
    cpu_start = time.process_time()

    try:
        while consumed < frames:
            latest = camera.read_latest(
                last_sequence,
                wait_timeout=1.0,
                copy_frame=True,
            )
            if latest is None:
                if camera.thread_alive:
                    continue
                raise RuntimeError(camera.metrics().get("last_error") or "camera stopped")
            if latest.repeated:
                continue
            if last_sequence is not None:
                skipped += max(0, latest.sequence - last_sequence - 1)
            last_sequence = latest.sequence
            consumed += 1
            preview = latest.frame

            if detector is not None:
                detector.submit(latest.frame, latest.timestamp)
                result, detect_metrics = detector.snapshot()
                preview, _valid = render_live_result(latest.frame, result)
                processed = int(detect_metrics["processed_frames"])
                if processed > last_processed:
                    detect_samples.append(float(detect_metrics["last_detect_ms"]))
                    last_processed = processed

            if display_enabled:
                cv2.imshow("Q1 Camera Benchmark", preview)
                displayed += 1
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
    finally:
        wall_end = time.perf_counter()
        cpu_end = time.process_time()
        camera_metrics = camera.metrics()
        if detector is not None:
            _result, final_detect = detector.snapshot()
            detector.close()
        else:
            final_detect = {}
        camera.close(release=True)
        cv2.destroyAllWindows()

    wall_s = max(wall_end - wall_start, 1e-9)
    detect_percentiles = _percentiles(detect_samples, (50, 95))
    result = {
        "hardware_run": True,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "platform": platform.platform(),
        "opencv_version": cv2.__version__,
        "opencv_num_threads": cv2.getNumThreads(),
        "mode": mode,
        "camera_index": camera_index,
        "camera": properties,
        "requested_width": width,
        "requested_height": height,
        "requested_fps": fps,
        "requested_fourcc": fourcc,
        "common_mode_probe": supported_mode_probe,
        "frames_displayed_or_consumed": consumed,
        "capture_fps": camera_metrics["capture_fps"],
        "display_fps": displayed / wall_s if display_enabled else 0.0,
        "detect_fps": float(final_detect.get("detect_fps", 0.0)),
        "read_ms_average": camera_metrics["read_ms_average"],
        "read_ms_p50": camera_metrics["read_ms_p50"],
        "read_ms_p95": camera_metrics["read_ms_p95"],
        "read_ms_p99": camera_metrics["read_ms_p99"],
        "detect_ms_p50": detect_percentiles["p50"],
        "detect_ms_p95": detect_percentiles["p95"],
        "possible_backlog_frames": skipped,
        "detector_dropped_frames": int(final_detect.get("dropped_frames", 0)),
        "failed_reads": camera_metrics["failed_reads"],
        "process_cpu_percent": (cpu_end - cpu_start) / wall_s * 100.0,
        "memory_rss_mb": _memory_rss_mb(),
        "result_age_ms": final_detect.get("result_age_ms"),
        "linux_diagnostics": _linux_camera_and_thermal_info(),
    }
    target = (
        Path(__file__).resolve().parents[2] / "reports"
        if report_dir is None
        else Path(report_dir)
    )
    json_path, md_path = _write_reports(result, target)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved: {json_path}")
    print(f"Saved: {md_path}")
    return result
