"""WHO reference table loading with checksum verification.

Tables are CSV conversions of the WHO Excel files (see MANIFEST.json and
scripts/build_reference_tables.py). Loading fails if a file's SHA-256 differs
from the manifest.
"""
from __future__ import annotations

import csv
import hashlib
import json
from bisect import bisect_left
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent / "reference_tables"

SEXES = ("male", "female")
AGE_INDICATORS = ("wfa", "lhfa")
LENHEI_INDICATORS = ("wfl", "wfh")


class TableIntegrityError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads((_DIR / "MANIFEST.json").read_text())


def _filename(indicator: str, sex: str) -> str:
    if indicator not in AGE_INDICATORS + LENHEI_INDICATORS or sex not in SEXES:
        raise KeyError((indicator, sex))
    return f"{indicator}_{'boys' if sex == 'male' else 'girls'}.csv"


def _read_verified(name: str) -> list[dict]:
    raw = (_DIR / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest()[name]["csv_sha256"]:
        raise TableIntegrityError(f"checksum mismatch for {name}")
    return list(csv.DictReader(raw.decode().splitlines()))


@lru_cache(maxsize=None)
def age_table(indicator: str, sex: str) -> tuple[tuple[float, float, float], ...]:
    """(L, M, S) per completed day of age, index = day."""
    rows = _read_verified(_filename(indicator, sex))
    out = []
    for i, r in enumerate(rows):
        if int(r["Day"]) != i:
            raise TableIntegrityError("age table days are not consecutive from 0")
        out.append((float(r["L"]), float(r["M"]), float(r["S"])))
    return tuple(out)


class LenHeiTable:
    """Weight-for-length/height table with linear interpolation between rows."""

    def __init__(self, rows: list[dict], key: str) -> None:
        self.x = [float(r[key]) for r in rows]
        self.lms = [(float(r["L"]), float(r["M"]), float(r["S"])) for r in rows]

    @property
    def min(self) -> float:
        return self.x[0]

    @property
    def max(self) -> float:
        return self.x[-1]

    def lookup(self, x: float) -> tuple[float, float, float] | None:
        """Interpolated (L, M, S), or None when x is outside the table range."""
        if x < self.x[0] or x > self.x[-1]:
            return None
        i = bisect_left(self.x, x)
        if self.x[i] == x:
            return self.lms[i]
        x0, x1 = self.x[i - 1], self.x[i]
        w = (x - x0) / (x1 - x0)
        return tuple(a + w * (b - a) for a, b in zip(self.lms[i - 1], self.lms[i]))  # type: ignore[return-value]


@lru_cache(maxsize=None)
def lenhei_table(indicator: str, sex: str) -> LenHeiTable:
    key = "Length" if indicator == "wfl" else "Height"
    return LenHeiTable(_read_verified(_filename(indicator, sex)), key)


# ---- Head circumference-for-age (R20) ----
# Two WHO tables per sex: weekly for 0 to 13 weeks, monthly for 0 to 60 months. L is 1 throughout, so the z-score is
# (y / M - 1) / S. Values between rows are interpolated linearly, as the weight-for-length table is.
HC_DAYS_PER_MONTH = 30.4375          # same constant as the engine (tested equal; engine imports this module)
HC_WEEKLY_MAX_DAYS = 91              # 13 weeks: the weekly table is used up to and including this day
HC_MAX_MONTHS = 60.0                 # the monthly table ends at 60 months (1826.25 days)


@lru_cache(maxsize=None)
def hc_table(sex: str, span: str) -> LenHeiTable:
    """`span` is '0_13' (weeks) or '0_5' (months). Checksum-verified like every other table."""
    if sex not in SEXES or span not in ("0_13", "0_5"):
        raise KeyError((sex, span))
    name = f"hcfa_{'boys' if sex == 'male' else 'girls'}_{span}.csv"
    return LenHeiTable(_read_verified(name), "Week" if span == "0_13" else "Month")


def hc_lms(sex: str, age_days: int) -> tuple[float, float, float] | None:
    """Interpolated (L, M, S) for head circumference at this age, or None past 60 months (1826 days)."""
    if age_days < 0:
        return None
    if age_days <= HC_WEEKLY_MAX_DAYS:
        return hc_table(sex, "0_13").lookup(age_days / 7.0)
    months = age_days / HC_DAYS_PER_MONTH
    if months > HC_MAX_MONTHS:
        return None
    return hc_table(sex, "0_5").lookup(months)
