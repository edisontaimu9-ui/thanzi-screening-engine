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
