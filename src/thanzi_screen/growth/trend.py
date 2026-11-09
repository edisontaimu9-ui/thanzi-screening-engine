"""Growth trends across two visits: change in WHO z-score for weight-for-age, length/height-for-age and head
circumference-for-age. Advisory only: never changes a classification (D9).

Standard library only. Stateless: the caller supplies the earlier visit. A trend flag is a prompt for a clinician to look,
not a diagnosis. The cut-offs come from the WHO technical guide (R21): a plotted line that crosses a z-score line, and the
-2 and -3 lines as the alert and severity cut-offs. The guide gives no number of SD for "crossing", so a fall of a full
z-score band (1.0 SD) is the engineering choice recorded as D168 / I64.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..anthro import tables
from ..anthro.lms import zscore_adjusted, zscore_plain
from .velocity import DAYS_PER_MONTH, MAX_AGE_DAYS, MIN_INTERVAL_DAYS

TREND_SD = 1.0                          # a full z-score band: the fall (or, for head size, the change) that is flagged
LENGTH_MAX_AGE_DAYS = 730               # same as the under-5 engine: lying length to 730 days, standing height after
LENHEI_OFFSET_CM = 0.7                  # same conversion the under-5 engine applies (tested equal)
PLAUSIBLE = {"wfa": (-6.0, 5.0), "lhfa": (-6.0, 6.0), "hcfa": (-5.0, 5.0)}   # first two equal the engine's; hcfa is I65
REFERENCES = {"wfa": "R5", "lhfa": "R4", "hcfa": "R20"}
GUIDE = "R21"
REVIEW_NOTE = "A clinician should review this child's growth."
ADVISORY = "Advisory only. It does not change the classification. A trained health worker decides."

NAMES = {"wfa": "weight_for_age", "lhfa": "length_height_for_age", "hcfa": "head_circumference_for_age"}
MESSAGES = {
    "interval_too_short": f"Too soon to judge the trend. Compare again after at least {MIN_INTERVAL_DAYS // 7} weeks.",
    "implausible_measurement": "A measurement looks implausible, so this trend was not assessed. Recheck both measurements.",
    "outside_reference_ages": "This trend could not be assessed: the age is outside the ages the WHO table covers.",
    "oedema_weight_unreliable": "Weight-for-age is not used when oedema is present, so this trend was not assessed.",
    "wfa_fell": ("Weight-for-age has fallen across z-score lines since the last visit. This may be a sign of growth "
                 "faltering. A health worker should check feeding, illness and the measurements."),
    "lhfa_fell": ("Length or height for age has fallen across z-score lines since the last visit. This may be a sign "
                  "of slowing linear growth (stunting). A health worker should check feeding, illness and the measurements."),
    "hcfa_fell": ("Head circumference for age has fallen across a z-score line since the last visit. A clinician should "
                  "check the measurement and the child."),
    "hcfa_rose": ("Head circumference for age has risen across a z-score line since the last visit. A clinician should "
                  "check the measurement and the child."),
    "below_minus2": "The latest value is newly below -2 SD on the WHO standard.",
    "below_minus3": "The latest value is newly below -3 SD on the WHO standard.",
}


@dataclass(frozen=True)
class PreviousVisit:
    """An earlier visit of the same child. Only age and weight are required."""
    age_days: int
    weight_kg: float
    length_height_cm: float | None = None
    measure_position: str | None = None          # "length" or "height"; required with length_height_cm
    hc_cm: float | None = None


@dataclass(frozen=True)
class IndicatorTrend:
    indicator: str                    # weight_for_age | length_height_for_age | head_circumference_for_age
    assessed: bool
    reason: str | None                # why it was not assessed (a key of MESSAGES), else None
    z_previous: float | None
    z_current: float | None
    z_change: float | None            # z_current - z_previous
    direction: str | None             # fell | rose | steady
    lines_crossed: tuple[int, ...]    # whole z-score lines (-3 to +3) between the two values
    status_change: str | None         # below_minus2 | below_minus3: newly below that line (weight and length only)
    flagged: bool
    messages: tuple[str, ...]
    reference: str
    guide: str = GUIDE


@dataclass(frozen=True)
class GrowthTrends:
    interval_days: int
    indicators: tuple[IndicatorTrend, ...]       # only the indicators with a measurement at both visits
    flagged: bool                                 # any indicator flagged
    advisory: str = ADVISORY


def _positive(name: str, v: object) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be a positive number")
    return float(v)


def _not_assessed(code: str, reason: str) -> IndicatorTrend:
    return IndicatorTrend(NAMES[code], False, reason, None, None, None, None, (), None, False, (MESSAGES[reason],),
                          REFERENCES[code])


def _z(code: str, sex: str, days: int, value: float, position: str | None) -> float | None:
    """z-score at one visit, or None when there is no table row for that age."""
    if code == "wfa":
        l, m, s = tables.age_table("wfa", sex)[days]
        return zscore_adjusted(value, m, l, s)
    if code == "lhfa":
        used = value
        if days <= LENGTH_MAX_AGE_DAYS and position == "height":
            used = value + LENHEI_OFFSET_CM
        elif days > LENGTH_MAX_AGE_DAYS and position == "length":
            used = value - LENHEI_OFFSET_CM
        used = round(used, 6)
        if not used > 0:
            return -99.0                                    # below any plausible limit: reported as implausible
        l, m, s = tables.age_table("lhfa", sex)[days]
        return zscore_plain(used, m, l, s)
    lms = tables.hc_lms(sex, days)
    if lms is None:
        return None
    l, m, s = lms
    return zscore_plain(value, m, l, s)


def _lines(z0: float, z1: float) -> tuple[int, ...]:
    """Whole z-score lines from -3 to +3 that lie between the two values (listed from the earlier value's side)."""
    if z1 < z0:
        return tuple(k for k in range(3, -4, -1) if z1 < k <= z0)
    return tuple(k for k in range(-3, 4) if z0 < k <= z1)


def _indicator(code: str, sex: str, prev_days: int, prev_value: float, days: int, value: float,
               prev_pos: str | None, pos: str | None, two_sided: bool) -> IndicatorTrend:
    z0 = _z(code, sex, prev_days, prev_value, prev_pos)
    z1 = _z(code, sex, days, value, pos)
    if z0 is None or z1 is None:
        return _not_assessed(code, "outside_reference_ages")
    lo, hi = PLAUSIBLE[code]
    if not (lo <= z0 <= hi and lo <= z1 <= hi):
        return _not_assessed(code, "implausible_measurement")
    change = round(z1 - z0, 6)
    fell, rose = change <= -TREND_SD, change >= TREND_SD
    status = None
    if not two_sided:                                       # the -2 and -3 lines are the guide's alert and severity cut-offs
        status = "below_minus3" if z0 >= -3 > z1 else "below_minus2" if z0 >= -2 > z1 else None
    flagged = fell or status is not None or (two_sided and rose)
    direction = "fell" if (fell or status) else "rose" if rose else "steady"
    msgs: list[str] = []
    if fell or (two_sided and rose) or status:
        msgs.append(MESSAGES[f"{code}_rose"] if direction == "rose" else MESSAGES[f"{code}_fell"])
        if status:
            msgs.append(MESSAGES[status])
    return IndicatorTrend(NAMES[code], True, None, round(z0, 2), round(z1, 2), round(change, 2), direction,
                          _lines(z0, z1), status, flagged, tuple(msgs), REFERENCES[code])


def assess_trends(sex: str, previous: PreviousVisit, age_days: int, weight_kg: float,
                  length_height_cm: float | None = None, measure_position: str | None = None,
                  hc_cm: float | None = None, oedema: bool = False) -> GrowthTrends:
    """Change in z-score between the earlier visit and this one, for each indicator measured at both visits.

    Weight-for-age is always possible (both visits have a weight); length or height needs both lengths with their
    positions; head circumference needs both head measurements. Raises ValueError for input that cannot be an interval
    (wrong types, non-positive values, earlier visit not before this one, a length without its position).
    A fall of 1.0 SD or more, or a new fall below -2 or -3 SD, is flagged for weight and length. Head circumference is
    flagged for a change of 1.0 SD or more in either direction, and has no single-value cut-off (the guide gives none)."""
    if sex not in ("male", "female"):
        raise ValueError("sex must be male or female")
    for v in (previous.age_days, age_days):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("ages must be whole numbers of days, zero or more")
    interval = age_days - previous.age_days
    if interval <= 0:
        raise ValueError("the earlier measurement must be before this visit")
    pw, cw = _positive("weight", previous.weight_kg), _positive("weight", weight_kg)
    pl = _positive("length", previous.length_height_cm) if previous.length_height_cm is not None else None
    cl = _positive("length", length_height_cm) if length_height_cm is not None else None
    ph = _positive("head circumference", previous.hc_cm) if previous.hc_cm is not None else None
    ch = _positive("head circumference", hc_cm) if hc_cm is not None else None
    for label, length, pos in (("previous", pl, previous.measure_position), ("current", cl, measure_position)):
        if length is not None and pos not in ("length", "height"):
            raise ValueError(f"{label} length needs its measure position (length or height)")

    wanted = [("wfa", pw, cw, None, None, False)]
    if pl is not None and cl is not None:
        wanted.append(("lhfa", pl, cl, previous.measure_position, measure_position, False))
    if ph is not None and ch is not None:
        wanted.append(("hcfa", ph, ch, None, None, True))

    out: list[IndicatorTrend] = []
    for code, v0, v1, p0, p1, two_sided in wanted:
        if interval < MIN_INTERVAL_DAYS:
            out.append(_not_assessed(code, "interval_too_short"))
        elif age_days > MAX_AGE_DAYS:
            out.append(_not_assessed(code, "outside_reference_ages"))
        elif code == "wfa" and oedema:
            out.append(_not_assessed(code, "oedema_weight_unreliable"))
        else:
            out.append(_indicator(code, sex, previous.age_days, v0, age_days, v1, p0, p1, two_sided))
    return GrowthTrends(interval, tuple(out), any(t.flagged for t in out))
