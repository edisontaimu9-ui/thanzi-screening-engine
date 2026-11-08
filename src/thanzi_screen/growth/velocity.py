"""Weight-gain velocity against the ASPEN reference ranges (R19). Advisory only: never changes a classification (D9).

Standard library only. Stateless: the caller supplies the earlier weight and age. The result is a comparison with a
published reference range, not a diagnosis. A weight gain below the range can be a sign of growth faltering, or a
measuring or recording problem; a person decides.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..anthro import tables
from ..anthro.lms import zscore_adjusted

DAYS_PER_MONTH = 30.4375                 # same constant as the under-5 engine
MAX_AGE_DAYS = 1856                      # last day the under-5 engine accepts (WHO: before 61 completed months)
MIN_INTERVAL_DAYS = 28                   # engineering choice, not from the reference (I60). See docs/modules/growth.md
WFA_PLAUSIBLE = (-6.0, 5.0)              # the same limits the under-5 engine uses (tested equal to anthro.engine)
REFERENCE_ID = "R19"
ADVISORY = "Advisory only. It does not change the classification. A trained health worker decides."

MESSAGES = {
    "below_range": ("Weight gain since the last visit is below the usual range for this age. This may be a sign of growth "
                    "faltering. A health worker should check feeding, illness and the measurements."),
    "weight_loss": ("The child weighs less than at the last visit. A health worker should check feeding, illness and the "
                    "measurements."),
    "interval_too_short": f"Too soon to judge weight gain. Compare again after at least {MIN_INTERVAL_DAYS // 7} weeks.",
    "implausible_weight": "A weight looks implausible, so weight gain was not assessed. Recheck both weights.",
    "reference_unverified": "Weight gain could not be assessed for this age and sex: the reference range is not confirmed yet.",
    "outside_reference_ages": "Weight gain could not be assessed: the interval goes outside the ages the reference covers.",
}


@dataclass(frozen=True)
class GrowthAssessment:
    assessed: bool
    reason: str | None                    # why it was not assessed (a key of MESSAGES), else None
    status: str | None                    # below_range | within_range | above_range
    interval_days: int
    weight_change_g: float | None
    rate_g_per_day: float | None
    reference_low: float | None           # g/day, averaged over the days of the interval in each age band
    reference_high: float | None
    flagged: bool                         # True only for below_range, including weight loss
    weight_loss: bool
    messages: tuple[str, ...]
    reference: str = REFERENCE_ID
    advisory: str = ADVISORY


@lru_cache(maxsize=1)
def _reference() -> dict:
    return json.loads((Path(__file__).with_name("aspen_weight_velocity.json")).read_text(encoding="utf-8"))


def _bands(sex: str) -> list[tuple[float, float, list[float] | None]]:
    key = "boys" if sex == "male" else "girls"
    return [(b["from_months"] * DAYS_PER_MONTH, b["to_months"] * DAYS_PER_MONTH, b[key]) for b in _reference()["bands"]]


def _plausible(sex: str, age_days: int, weight_kg: float) -> bool:
    l, m, s = tables.age_table("wfa", sex)[age_days]
    z = zscore_adjusted(weight_kg, m, l, s)
    return WFA_PLAUSIBLE[0] <= z <= WFA_PLAUSIBLE[1]


def _not_assessed(reason: str, interval: int, **kw) -> GrowthAssessment:
    return GrowthAssessment(False, reason, None, interval, kw.get("change"), kw.get("rate"), None, None, False, False,
                            (MESSAGES[reason],))


def assess_weight_velocity(sex: str, previous_age_days: int, previous_weight_kg: float,
                           age_days: int, weight_kg: float) -> GrowthAssessment:
    """Compare the average daily weight change with the reference range for the ages in between.

    Raises ValueError for input that cannot be an interval (wrong types, non-positive weights, previous not earlier).
    The range is averaged over the days the interval spends in each age band, so an interval that crosses a band edge is
    compared with a blend of the two ranges."""
    if sex not in ("male", "female"):
        raise ValueError("sex must be male or female")
    for v in (previous_age_days, age_days):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("ages must be whole numbers of days, zero or more")
    for v in (previous_weight_kg, weight_kg):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError("weights must be positive numbers")
    interval = age_days - previous_age_days
    if interval <= 0:
        raise ValueError("the earlier measurement must be before this visit")
    if interval < MIN_INTERVAL_DAYS:
        return _not_assessed("interval_too_short", interval)
    if age_days > MAX_AGE_DAYS:
        return _not_assessed("outside_reference_ages", interval)
    if not (_plausible(sex, previous_age_days, previous_weight_kg) and _plausible(sex, age_days, weight_kg)):
        return _not_assessed("implausible_weight", interval)

    change_g = round((weight_kg - previous_weight_kg) * 1000.0, 6)      # rounded so a gain exactly on a range end is not
    rate = round(change_g / interval, 6)                                  # pushed outside it by floating-point error
    low = high = covered = 0.0
    for start, end, rng in _bands(sex):
        days = min(end, age_days) - max(start, previous_age_days)
        if days <= 0:
            continue
        if rng is None:
            return _not_assessed("reference_unverified", interval, change=round(change_g, 1), rate=round(rate, 2))
        low, high, covered = low + rng[0] * days, high + rng[1] * days, covered + days
    if covered < interval - 1e-6:
        return _not_assessed("outside_reference_ages", interval, change=round(change_g, 1), rate=round(rate, 2))
    low, high = round(low / interval, 6), round(high / interval, 6)
    status = "below_range" if rate < low else "above_range" if rate > high else "within_range"
    loss = weight_kg < previous_weight_kg
    msgs = (MESSAGES["weight_loss"],) if loss else (MESSAGES["below_range"],) if status == "below_range" else ()
    return GrowthAssessment(True, None, status, interval, round(change_g, 1), round(rate, 2), round(low, 2), round(high, 2),
                            status == "below_range", loss, msgs)
