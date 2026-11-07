"""LMS z-score mathematics (WHO Child Growth Standards).

Documented in WHO Child Growth Standards: Methods and Development, ch. 7
(register R6). Pure functions, no I/O.
"""
from __future__ import annotations

import math


def sd_value(m: float, l: float, s: float, k: float) -> float:
    """Measurement value at k standard deviations: M * (1 + L*S*k) ** (1/L)."""
    if l == 0:
        return m * math.exp(s * k)
    base = 1 + l * s * k
    if base <= 0:
        raise ValueError("invalid LMS parameters: non-positive base")
    return m * base ** (1 / l)


def zscore_plain(y: float, m: float, l: float, s: float) -> float:
    """Unadjusted LMS z-score: ((y/M)**L - 1) / (L*S)."""
    if y <= 0 or m <= 0 or s <= 0:
        raise ValueError("y, M and S must be positive")
    if l == 0:
        return math.log(y / m) / s
    return ((y / m) ** l - 1) / (l * s)


def zscore_adjusted(y: float, m: float, l: float, s: float) -> float:
    """WHO adjusted z-score for weight-based indicators.

    Within +/-3 it equals the plain z-score. Beyond +/-3 the z-score is extended
    linearly using the distance between the +2/+3 (or -2/-3) SD values.
    """
    z = zscore_plain(y, m, l, s)
    if z > 3:
        sd3 = sd_value(m, l, s, 3)
        sd23 = sd3 - sd_value(m, l, s, 2)
        return 3 + (y - sd3) / sd23
    if z < -3:
        sd3n = sd_value(m, l, s, -3)
        sd23n = sd_value(m, l, s, -2) - sd3n
        return -3 + (y - sd3n) / sd23n
    return z
