"""Q1 TTL camera smoke test — no robot motion.

Usage:
  python -m q1.camera_ttl_smoke_test
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2

from .k230_ttl_camera_adapter import K230TtlQ1Camera


def main() -> int:
    out = Path("runs/q1/ttl_smoke")
    out.mkdir(parents=True, exist_ok=True)
    cam = K230TtlQ1Camera(output_dir=out)
    try:
        cam.open()
        rows = []
        for i in range(1, 6):
            t0 = time.perf_counter()
            snap = cam.capture_snapshot(i)
            dt = (time.perf_counter() - t0) * 1000.0
            jpg = out / f"smoke_{i:02d}.jpg"
            cv2.imwrite(str(jpg), snap.frame)
            ttl = (snap.metadata or {}).get("k230_ttl") or {}
            row = {
                "i": i,
                "shape": list(snap.frame.shape),
                "wall_ms": dt,
                "session_id": ttl.get("session_id"),
                "request_id": ttl.get("request_id"),
                "frame_id": ttl.get("frame_id"),
                "jpeg_bytes": ttl.get("jpeg_bytes"),
                "capture_ms": ttl.get("capture_ms"),
                "encode_ms": ttl.get("encode_ms"),
                "receive_ms": ttl.get("receive_ms"),
                "decode_ms": ttl.get("decode_ms"),
                "total_ms": ttl.get("total_ms"),
                "crc_ok": ttl.get("crc_ok"),
                "saved": str(jpg),
            }
            rows.append(row)
            print(json.dumps(row, indent=2, ensure_ascii=False), flush=True)
        ok = all(r["shape"][:2] == [720, 1280] for r in rows)
        print(json.dumps({"pass": ok, "n": len(rows)}, indent=2))
        return 0 if ok else 4
    finally:
        cam.close()


if __name__ == "__main__":
    raise SystemExit(main())
