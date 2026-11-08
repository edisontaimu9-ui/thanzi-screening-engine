"""Hardware awareness for training and inference. Standard library only, never raises on odd systems.

Training here is single-threaded plain Python, so the limit is time, not memory. `recommend_preset` picks the
largest architecture whose estimated training time fits a budget. The estimate is rough (aim: within about 2x).
Nothing from this module is written into model files or model cards, so artifacts stay reproducible.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from operator import mul

from .network import PRESETS, parameter_count

# Measured on one machine: a training step costs about this many times the multiply-adds of one forward pass.
TRAIN_OVERHEAD = 4.0


@dataclass(frozen=True)
class HardwareProfile:
    cpu_count: int
    memory_mb: int | None          # None when the system does not say (some Android builds hide /proc/meminfo)
    macs_per_second: float         # measured pure-Python multiply-adds per second


def _memory_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def measure_speed(budget_seconds: float = 0.15) -> float:
    """Pure-Python multiply-adds per second, from a short fixed loop shaped like one dense layer."""
    x = [0.5 + i * 0.01 for i in range(32)]
    w = [[0.01 * (i + j) for i in range(32)] for j in range(32)]
    done, start = 0, time.perf_counter()
    while True:
        for _ in range(20):
            [sum(map(mul, r, x)) for r in w]
        done += 20 * 32 * 32
        elapsed = time.perf_counter() - start
        if elapsed >= budget_seconds:
            return done / elapsed


def detect_hardware(speed_budget_seconds: float = 0.15) -> HardwareProfile:
    return HardwareProfile(os.cpu_count() or 1, _memory_mb(), measure_speed(speed_budget_seconds))


def estimate_train_seconds(hw: HardwareProfile, rows: int, n_inputs: int, hidden, epochs: int, n_out: int = 1) -> float:
    macs = parameter_count(n_inputs, hidden, n_out)
    return rows * epochs * macs * TRAIN_OVERHEAD / hw.macs_per_second


def recommend_preset(hw: HardwareProfile, rows: int, n_inputs: int, epochs: int = 30, budget_seconds: float = 900.0) -> str:
    """Largest preset that trains within the budget. Falls back to `tiny`. Very low memory also forces `tiny`."""
    if hw.memory_mb is not None and hw.memory_mb < 512:
        return "tiny"
    best = "tiny"
    for name in ("small", "base"):                                   # PRESETS order: tiny < small < base
        if estimate_train_seconds(hw, rows, n_inputs, PRESETS[name], epochs) <= budget_seconds:
            best = name
    return best
