#!/usr/bin/env python3
"""1280x720 stress / long-run capture test."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from k230_camera import K230TtlSnapshotCamera  # noqa: E402
from protocol import DEFAULT_TTL_BY_ID  # noqa: E402


def percentile(vals, p):
    if not vals:
        return None
    s = sorted(vals)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=DEFAULT_TTL_BY_ID)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--interval", type=float, default=0.05)
    ap.add_argument("--json-out", default="")
    ap.add_argument("--log", default=str(Path.home() / "k230_ttl_camera" / "logs" / "stress.jsonl"))
    args = ap.parse_args()

    ok = fail = 0
    raw_fail = 0
    recovered = 0
    totals = []
    sizes = []
    errors = []
    with K230TtlSnapshotCamera(port=args.port, log_path=Path(args.log)) as cam:
        for i in range(1, args.count + 1):
            try:
                frame = cam.capture_snapshot()
                meta = cam.last_meta
                assert frame is not None and meta is not None
                assert frame.shape[1] == 1280 and frame.shape[0] == 720
                ok += 1
                totals.append(meta.total_ms)
                sizes.append(meta.jpeg_bytes)
                if meta.retry_count:
                    recovered += 1
                    raw_fail += 1
                if i <= 3 or i % 10 == 0:
                    print(
                        f"OK {i}/{args.count} fid={meta.frame_id} "
                        f"len={meta.jpeg_bytes} total={meta.total_ms:.1f}ms retry={meta.retry_count}",
                        flush=True,
                    )
            except Exception as e:
                fail += 1
                raw_fail += 1
                errors.append({"i": i, "err": str(e)})
                print(f"FAIL {i} {e}", flush=True)
            time.sleep(args.interval)

    # original success = requests that succeeded without retry
    original_ok = ok - recovered
    res = {
        "count": args.count,
        "ok": ok,
        "fail": fail,
        "raw_fail_events": raw_fail,
        "original_success": original_ok,
        "retry_recovered": recovered,
        "original_success_rate": original_ok / args.count if args.count else 0,
        "final_success_rate": ok / args.count if args.count else 0,
        "avg_ms": statistics.mean(totals) if totals else None,
        "p95_ms": percentile(totals, 95),
        "p99_ms": percentile(totals, 99),
        "max_ms": max(totals) if totals else None,
        "avg_jpeg": statistics.mean(sizes) if sizes else None,
        "max_jpeg": max(sizes) if sizes else None,
        "errors": errors[:30],
        "pass": fail == 0 and ok == args.count,
    }
    print(json.dumps(res, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    return 0 if res["pass"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
