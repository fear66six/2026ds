#!/usr/bin/env python3
"""Hardware smoke test: 5 captures at fixed 1280x720."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from k230_camera import K230TtlSnapshotCamera  # noqa: E402
from protocol import DEFAULT_TTL_BY_ID  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_TTL_BY_ID)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--captures-dir", default=str(Path.home() / "k230_ttl_camera" / "captures"))
    ap.add_argument("--log", default=str(Path.home() / "k230_ttl_camera" / "logs" / "smoke.jsonl"))
    args = ap.parse_args()
    cap_dir = Path(args.captures_dir)
    cap_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with K230TtlSnapshotCamera(port=args.port, log_path=Path(args.log)) as cam:
        if not cam.health_check():
            print("health_check failed")
            return 2
        for i in range(1, args.count + 1):
            t0 = time.perf_counter()
            frame = cam.capture_snapshot()
            dt = (time.perf_counter() - t0) * 1000.0
            meta = cam.last_meta
            out = cap_dir / f"smoke_{i:03d}.jpg"
            import cv2

            cv2.imwrite(str(out), frame)
            row = {
                "i": i,
                "shape": list(frame.shape),
                "total_wall_ms": dt,
                "meta": None if meta is None else meta.__dict__,
                "saved": str(out),
            }
            results.append(row)
            print(json.dumps(row, indent=2), flush=True)
    ok = all(r["meta"] and r["shape"][0] == 720 and r["shape"][1] == 1280 for r in results)
    print(json.dumps({"pass": ok, "n": len(results)}, indent=2))
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
