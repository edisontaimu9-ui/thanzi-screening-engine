"""Area-level hotspot surveillance (add-on). Advisory only, standard library only, stateless.

Input is counts per district per month that the caller has already grouped (Hope's backend owns the database and the
GROUP BY). No child record, identifier, date of birth or fine geography is accepted. Output never changes a child's
classification. Thresholds live in hotspot_config.json and are placeholders until the Ministry confirms them.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("hotspot_config.json")
CONFIG: dict = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
CONFIG_VERSION: str = CONFIG["version"]

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DISTRICT_RE = re.compile(r"^[A-Za-z][A-Za-z '\-]{0,58}$")
ADVISORY = ("Hotspot flags are advisory and describe children who were screened, not the whole population. "
            "They support planning and never change an individual child's classification or referral.")

HOTSPOT, WATCH, NOT_FLAGGED, INSUFFICIENT, NO_DATA = (
    "hotspot", "watch", "not_flagged", "insufficient_data", "no_data")
_ORDER = {HOTSPOT: 0, WATCH: 1, NOT_FLAGGED: 2, INSUFFICIENT: 3, NO_DATA: 4}


class SurveillanceInputError(ValueError):
    """Bad input. `code` is stable and the message never contains submitted values."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class Row:
    district: str
    period: str
    screened: int
    sam: int
    mam: int
    unable: int = 0


def wilson(cases: int, n: int, z: float) -> tuple[float, float]:
    """Wilson score interval for a proportion. Stable for small n and for 0 or n cases."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = cases / n
    z2 = z * z
    centre = (p + z2 / (2 * n)) / (1 + z2 / n)
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / (1 + z2 / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def _two_prop_z(c1: int, n1: int, c2: int, n2: int) -> float:
    pooled = (c1 + c2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    return 0.0 if se == 0 else (c1 / n1 - c2 / n2) / se


def validate(rows: list[Row], reference_rate: float | None) -> None:
    if not rows:
        raise SurveillanceInputError("no_rows", "At least one row is needed.")
    if len(rows) > CONFIG["max_rows"]:
        raise SurveillanceInputError("too_many_rows", "Too many rows in one request.")
    if reference_rate is not None and not (0.0 < reference_rate < 1.0):
        raise SurveillanceInputError("invalid_reference_rate", "reference_rate must be between 0 and 1.")
    seen: set[tuple[str, str]] = set()
    for r in rows:
        if not DISTRICT_RE.match(r.district) or not r.district.strip():
            raise SurveillanceInputError("invalid_district", "A district name has an invalid format.")
        if not PERIOD_RE.match(r.period):
            raise SurveillanceInputError("invalid_period", "A period must be YYYY-MM.")
        if min(r.screened, r.sam, r.mam, r.unable) < 0 or r.screened > 10_000_000:
            raise SurveillanceInputError("invalid_count", "Counts must be whole numbers from 0 to 10,000,000.")
        if r.sam + r.mam + r.unable > r.screened:
            raise SurveillanceInputError("inconsistent_counts", "sam + mam + unable cannot exceed screened.")
        key = (r.district.strip().lower(), r.period)
        if key in seen:
            raise SurveillanceInputError("duplicate_row", "Each district and period may appear once.")
        seen.add(key)


def _prev_period(history: list[Row], current: str) -> Row | None:
    earlier = [r for r in history if r.period < current]
    return max(earlier, key=lambda r: r.period) if earlier else None


def assess(rows: list[Row], reference_rate: float | None = None) -> dict:
    """Assess every district for the latest period in `rows`. Pure function."""
    validate(rows, reference_rate)
    cfg = CONFIG
    z, min_n = cfg["confidence_z"], cfg["min_screened"]
    period = max(r.period for r in rows)
    by_district: dict[str, list[Row]] = {}
    for r in rows:
        by_district.setdefault(r.district.strip(), []).append(r)
    current = {d: next((r for r in rs if r.period == period), None) for d, rs in by_district.items()}
    tot_n = sum(r.screened for r in current.values() if r)
    tot_c = sum(r.sam + r.mam for r in current.values() if r)

    areas = []
    for d, cur in current.items():
        out = {"district": d, "status": NO_DATA, "screened": None, "sam": None, "mam": None, "gam_cases": None,
               "prevalence": None, "ci_low": None, "ci_high": None, "reference_rate": None, "trend": "not_assessed",
               "previous_prevalence": None, "reference_kind": None, "data_quality_review": False,
               "counts_suppressed": False, "reasons": []}
        if cur is None:
            out["reasons"].append("no_row_for_latest_period")
            areas.append(out)
            continue
        out["screened"] = cur.screened
        cases = cur.sam + cur.mam
        if cur.screened < min_n:
            out.update(status=INSUFFICIENT)
            out["reasons"].append("fewer_than_min_screened")
            areas.append(out)
            continue
        if cur.screened and cur.unable / cur.screened >= cfg["unable_share_review"]:
            out["data_quality_review"] = True
            out["reasons"].append("high_share_unable_to_classify")
        ref = reference_rate
        ref_kind = "supplied"
        if ref is None:
            rest_n = tot_n - cur.screened
            ref = (tot_c - cases) / rest_n if rest_n >= min_n else None
            ref_kind = "batch_leave_one_out"
        lo, hi = wilson(cases, cur.screened, z)
        p = cases / cur.screened
        out.update(screened=cur.screened, sam=cur.sam, mam=cur.mam, gam_cases=cases, prevalence=round(p, 4),
                   ci_low=round(lo, 4), ci_high=round(hi, 4), reference_rate=None if ref is None else round(ref, 4),
                   reference_kind=ref_kind)
        prev = _prev_period(by_district[d], period)
        rising = False
        if prev and prev.screened >= min_n:
            pc = prev.sam + prev.mam
            out["previous_prevalence"] = round(pc / prev.screened, 4)
            zz = _two_prop_z(cases, cur.screened, pc, prev.screened)
            out["trend"] = "rising" if zz >= cfg["trend_z"] else "falling" if zz <= -cfg["trend_z"] else "steady"
            rising = out["trend"] == "rising"
        # status
        above_ref = ref is not None and lo > ref
        if above_ref and p >= cfg["min_prevalence_for_hotspot"]:
            out["status"] = HOTSPOT
            out["reasons"].append("prevalence_significantly_above_reference")
        elif (ref is not None and p > ref) or rising:
            out["status"] = WATCH
            out["reasons"].append("rising_prevalence" if rising else "above_reference_not_significant")
        else:
            out["status"] = NOT_FLAGGED
        if ref is None:
            out["reasons"].append("no_reference_available")
        # Small-cell suppression (display safety). Counts and rates are withheld, the status is kept so a real hotspot
        # is not hidden. The status is computed before suppression and reveals only a threshold, never a count.
        if any(0 < v < cfg["suppress_cells_below"] for v in (cur.sam, cur.mam)):
            for k in ("sam", "mam", "gam_cases", "prevalence", "ci_low", "ci_high", "previous_prevalence"):
                out[k] = None
            out["counts_suppressed"] = True
            out["reasons"].append("small_cell_suppressed")
        areas.append(out)

    areas.sort(key=lambda a: (_ORDER[a["status"]], -(a["prevalence"] or 0.0), a["district"]))
    summary = {s: sum(1 for a in areas if a["status"] == s) for s in _ORDER}
    return {"period": period, "config_version": CONFIG_VERSION, "areas": areas, "summary": summary,
            "min_screened": min_n, "advisory": ADVISORY}
