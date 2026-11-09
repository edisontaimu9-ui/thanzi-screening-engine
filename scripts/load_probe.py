"""Small load probe for POST /v1/screen. Standard library only. Synthetic requests only.

    python scripts/load_probe.py --base-url http://127.0.0.1:8080 --gateway-key "$THANZI_GATEWAY_KEY" \
        --concurrency 4 --requests 2000

Reports status counts, latency percentiles and throughput for the stated concurrency. It sets no pass or fail
threshold: targets need the expected load and the target server specification. Record the
environment (CPU, memory, container limits, workers) next to any numbers you keep. Do not point it at a shared or
production service without the owner's agreement.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import statistics
import sys
import threading
import time
from urllib.parse import urlparse

BASE = {"sex": "male", "age_days": 500, "weight_kg": 9.5, "length_height_cm": 75.0, "measure_position": "length",
        "oedema": "none", "muac_cm": 14.0, "appetite": "passed", "danger_signs": [], "complications": [],
        "clinically_well_and_alert": True}
PAYLOADS = [
    BASE,
    {**BASE, "muac_cm": 12.0},
    {**BASE, "muac_cm": 11.0},
    {**BASE, "muac_cm": 12.0, "hiv_positive": True},
    {**BASE, "oedema": "+++", "muac_cm": None},
    {**BASE, "sex": "female", "age_days": 100, "weight_kg": 5.5, "length_height_cm": 60.0, "muac_cm": None,
     "danger_signs": [], "complications": [], "visible_severe_wasting": False, "too_weak_to_suckle": False,
     "failure_to_gain_weight": False},
]


def percentile(sorted_ms: list[float], p: float) -> float:
    if not sorted_ms:
        return float("nan")
    k = min(len(sorted_ms) - 1, max(0, round(p / 100 * (len(sorted_ms) - 1))))
    return sorted_ms[k]


def worker(host: str, port: int, key: str, view: str, count: int, offset: int, out: list, errors: list) -> None:
    conn = http.client.HTTPConnection(host, port, timeout=30)
    headers = {"Content-Type": "application/json", "X-Gateway-Key": key}
    for i in range(count):
        body = json.dumps(PAYLOADS[(offset + i) % len(PAYLOADS)])
        t0 = time.perf_counter()
        try:
            conn.request("POST", f"/v1/screen?view={view}", body=body, headers=headers)
            resp = conn.getresponse()
            resp.read()
            status = resp.status
        except Exception as exc:                      # connection errors are counted, not hidden
            errors.append(type(exc).__name__)
            conn.close()
            conn = http.client.HTTPConnection(host, port, timeout=30)
            continue
        out.append((status, (time.perf_counter() - t0) * 1000.0))
    conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--gateway-key", default=os.environ.get("THANZI_GATEWAY_KEY"))
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--requests", type=int, default=1000, help="total requests across all workers")
    ap.add_argument("--warmup", type=int, default=50)
    ap.add_argument("--view", choices=("worker", "audit"), default="worker", help="audit needs --audit-key support in your gateway; default worker")
    args = ap.parse_args()
    if not args.gateway_key:
        print("a gateway key is required (--gateway-key or THANZI_GATEWAY_KEY)", file=sys.stderr)
        return 2
    u = urlparse(args.base_url)
    host, port = u.hostname or "127.0.0.1", u.port or 80

    warm: list = []
    worker(host, port, args.gateway_key, args.view, args.warmup, 0, warm, [])
    results: list = []
    errors: list = []
    per = max(1, args.requests // args.concurrency)
    threads = [threading.Thread(target=worker, args=(host, port, args.gateway_key, args.view, per, n, results, errors))
               for n in range(args.concurrency)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.perf_counter() - t0

    codes: dict[int, int] = {}
    for status, _ in results:
        codes[status] = codes.get(status, 0) + 1
    ms = sorted(m for s, m in results if s == 200)
    total = per * args.concurrency
    print(f"requests sent: {total}  completed: {len(results)}  connection errors: {len(errors)}  concurrency: {args.concurrency}")
    print("status counts: " + ", ".join(f"{k}: {v}" for k, v in sorted(codes.items())))
    if ms:
        print(f"latency ms (200 only): min {ms[0]:.1f}  mean {statistics.mean(ms):.1f}  p50 {percentile(ms, 50):.1f}  "
              f"p95 {percentile(ms, 95):.1f}  p99 {percentile(ms, 99):.1f}  max {ms[-1]:.1f}")
    print(f"wall time {wall:.2f} s  throughput {len(results) / wall:.1f} requests/s")
    bad = len(errors) + sum(v for k, v in codes.items() if k != 200)
    print("no errors" if bad == 0 else f"{bad} requests did not return 200")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
