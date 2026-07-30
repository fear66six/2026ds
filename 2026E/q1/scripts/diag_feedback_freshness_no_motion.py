"""No-motion NexArm feedback freshness diagnostic.

Opens the serial port and issues get_current_coords only.
Never calls set_pose or any motion command.
"""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    cfg = json.loads(
        (project_root / "q1/config/robot_config.json").read_text(encoding="utf-8")
    )
    port = cfg["nexarm_port"]
    sdk_path = project_root / "hardware/nexarm/jetson_to_nexarm/nexarm_sdk.py"
    spec = importlib.util.spec_from_file_location("diag_nexarm_sdk", sdk_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load SDK: {sdk_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod.NexArmClient, "flush_input_buffer"):
        raise RuntimeError("flush_input_buffer missing from deployed SDK")

    client = mod.NexArmClient(port)
    client.open()
    try:
        firmware = client.get_firmware_version(timeout=1.0)
        samples = []
        for index in range(3):
            discarded = client.flush_input_buffer()
            started = time.monotonic()
            coords = client.get_current_coords(timeout=1.0)
            ended = time.monotonic()
            meta = dict(getattr(coords, "meta", {}) or {})
            sample = {
                "i": index,
                "pose": [
                    coords.x,
                    coords.y,
                    coords.z,
                    coords.pitch,
                    coords.roll,
                    coords.claw,
                ],
                "servos": list(getattr(coords, "servo_positions", ()) or ()),
                "flush_before_extra": discarded,
                "meta": meta,
                "host_span_s": round(ended - started, 4),
            }
            if meta.get("request_started_s") is None:
                raise RuntimeError(f"missing request timestamp: {sample}")
            if meta.get("response_received_s") is None:
                raise RuntimeError(f"missing response timestamp: {sample}")
            if meta["response_received_s"] < meta["request_started_s"]:
                raise RuntimeError(f"response before request: {sample}")
            if (meta["response_received_s"] - meta["request_started_s"]) >= 1.0:
                raise RuntimeError(f"response latency too large: {sample}")
            samples.append(sample)
            time.sleep(0.15)
        payload = {
            "mode": "NO_MOTION_FEEDBACK_DIAG",
            "port": port,
            "firmware_version": firmware,
            "direct_pick_release_pose_verified": cfg.get(
                "direct_pick_release_pose_verified"
            ),
            "samples": samples,
            "verdict": "PASS_REQUEST_BOUND_COORDS_REPLIES",
            "note": (
                "No set_pose was sent. This only proves post-flush replies carry "
                "request/response timestamps."
            ),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
