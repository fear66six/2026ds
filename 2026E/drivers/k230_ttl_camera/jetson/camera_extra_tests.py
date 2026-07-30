#!/usr/bin/env python3
"""Session restart / client restart / freshness helpers (hardware)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from k230_camera import K230TtlSnapshotCamera  # noqa: E402
from protocol import DEFAULT_TTL_BY_ID  # noqa: E402


def client_restart_test(n: int = 10) -> dict:
    rows = []
    for i in range(1, n + 1):
        cam = K230TtlSnapshotCamera(port=DEFAULT_TTL_BY_ID)
        try:
            cam.initialize()
            frame = cam.capture_snapshot()
            meta = cam.last_meta
            rows.append(
                {
                    "i": i,
                    "ok": True,
                    "session_id": meta.session_id if meta else None,
                    "frame_id": meta.frame_id if meta else None,
                    "shape": list(frame.shape),
                }
            )
        except Exception as e:
            rows.append({"i": i, "ok": False, "error": str(e)})
        finally:
            cam.close()
            time.sleep(0.3)
    ok = sum(1 for r in rows if r.get("ok"))
    return {"test": "client_restart", "n": n, "ok": ok, "pass": ok == n, "rows": rows}


def freshness_test() -> dict:
    """Compare mean abs diff between two captures; user should change lighting between prompts."""
    with K230TtlSnapshotCamera(port=DEFAULT_TTL_BY_ID) as cam:
        print("CAPTURE A — keep current scene", flush=True)
        a = cam.capture_snapshot()
        ma = cam.last_meta
        print("Change scene brightness now (cover/uncover lens). Waiting 5s...", flush=True)
        time.sleep(5.0)
        print("CAPTURE B", flush=True)
        b = cam.capture_snapshot()
        mb = cam.last_meta
    mad = float(np.mean(np.abs(a.astype(np.float32) - b.astype(np.float32))))
    res = {
        "test": "freshness",
        "mad": mad,
        "request_ids": [ma.request_id, mb.request_id],
        "frame_ids": [ma.frame_id, mb.frame_id],
        "capture_ts": [ma.capture_timestamp_ms, mb.capture_timestamp_ms],
        "session_id": ma.session_id,
        "pass": (
            mad > 5.0
            and ma.request_id != mb.request_id
            and mb.frame_id > ma.frame_id
            and mb.capture_timestamp_ms != ma.capture_timestamp_ms
        ),
    }
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("client_restart", "freshness"), required=True)
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()
    if args.mode == "client_restart":
        res = client_restart_test(args.count)
    else:
        res = freshness_test()
    print(json.dumps(res, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0 if res.get("pass") else 4


if __name__ == "__main__":
    raise SystemExit(main())
