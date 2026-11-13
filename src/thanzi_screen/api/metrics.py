"""Operational counters for the gateway to read (D176). Framework-free, standard library only.

What it keeps: how many requests each route received, how many got each status code, and how long `/v1/screen` took.
What it never keeps: a body, a header, a value, an address, a key or anything about a child. Counts and durations only.
Held in memory for this process: lost on restart, and each worker process counts its own requests.
"""
from __future__ import annotations

import math
import threading
import time
from collections import deque

# Fixed route labels, so a caller cannot grow the table by requesting made-up paths.
KNOWN_PATHS = frozenset({"/health", "/version", "/v1/about", "/v1/metrics", "/v1/screen",
                         "/v1/llm/health", "/v1/llm/generate", "/v1/surveillance/hotspots", "/v1/report",
                         "/v1/surveillance/report", "/v1/surveillance/dhis2"})
LATENCY_WINDOW = 1000          # the most recent /v1/screen calls the percentiles are taken over
SCREEN_PATH = "/v1/screen"


def label(path: str) -> str:
    return path if path in KNOWN_PATHS else "other"


def _percentile(sorted_ms: list[float], q: float) -> float:
    """Nearest-rank percentile of an already sorted, non-empty list."""
    rank = max(1, math.ceil(round(q * len(sorted_ms), 9)))
    return sorted_ms[min(rank, len(sorted_ms)) - 1]


class Metrics:
    def __init__(self, clock=time.time, monotonic=time.monotonic) -> None:
        self._lock = threading.Lock()
        self._clock, self._mono = clock, monotonic
        self.started_at = clock()
        self._t0 = monotonic()
        self._by_route: dict[str, int] = {}
        self._by_status: dict[str, int] = {}
        self._screen_ms: deque[float] = deque(maxlen=LATENCY_WINDOW)

    def record(self, path: str, status: int, seconds: float) -> None:
        route = label(path)
        with self._lock:
            self._by_route[route] = self._by_route.get(route, 0) + 1
            self._by_status[str(status)] = self._by_status.get(str(status), 0) + 1
            if route == SCREEN_PATH:
                self._screen_ms.append(seconds * 1000.0)

    def uptime_seconds(self) -> float:
        return self._mono() - self._t0

    def snapshot(self) -> dict:
        with self._lock:
            by_route, by_status, ms = dict(self._by_route), dict(self._by_status), sorted(self._screen_ms)
        total = sum(by_status.values())
        server_errors = sum(n for s, n in by_status.items() if s.startswith("5"))
        screen = {"calls_measured": len(ms), "window": LATENCY_WINDOW,
                  "p50_ms": None, "p95_ms": None, "max_ms": None, "mean_ms": None}
        if ms:
            screen.update(p50_ms=round(_percentile(ms, 0.50), 2), p95_ms=round(_percentile(ms, 0.95), 2),
                          max_ms=round(ms[-1], 2), mean_ms=round(sum(ms) / len(ms), 2))
        return {"since": self.started_at, "uptime_seconds": round(self.uptime_seconds(), 1),
                "requests_total": total, "server_errors": server_errors,
                "by_route": by_route, "by_status": by_status, "screen_latency": screen}
