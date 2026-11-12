"""Growth velocity and growth faltering across any number of visits.

Per interval (consecutive visits at least min_interval_days apart) it reports:
- weight velocity in g per day against the ASPEN reference range (thanzi_screen.growth, reused unchanged);
- the change in WAZ, HAZ and WHZ, in SD and in SD per month.

Faltering definitions (all configurable in FalteringConfig). There is no single published definition for a 0 to 59 month
programme, so the defaults are engineering choices, consistent with thanzi_screen.growth.trend, and are NOT clinical
guidance. They need review by a clinician before any real use.

- weight faltering:  an interval with weight below the ASPEN range or weight loss, or a WAZ fall of fall_sd or more.
- linear faltering:  an interval with a HAZ fall of fall_sd or more, or a new fall below -2 or -3.
- wasting faltering: an interval with a WHZ fall of fall_sd or more, or a new fall below -2 or -3.
- sustained:         the same kind flagged in two consecutive intervals.
- cumulative:        a fall of fall_sd or more from the best value inside the last cumulative_window_days.

Level: none | possible (one flagged interval or a cumulative fall) | sustained. Missing or implausible data never produce
"none": the result says not assessable. Advisory only: nothing here changes a CMAM classification.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..factors import ChildRecord
from ..growth import assess_weight_velocity
from .indicators import IndicatorPanel, compute_panel
from ..anthro import InputError

DAYS_PER_MONTH = 30.4375
ADVISORY = "Advisory only. It does not change the classification. A trained health worker decides."


@dataclass(frozen=True)
class FalteringConfig:
    fall_sd: float = 1.0                 # engineering choice, same as growth.trend.TREND_SD
    min_interval_days: int = 28          # same as growth.velocity.MIN_INTERVAL_DAYS
    max_interval_days: int = 270         # longer gaps are not judged as one interval: too coarse to call velocity
    cumulative_window_days: int = 180
    sustained_intervals: int = 2


@dataclass(frozen=True)
class IntervalGrowth:
    from_age_days: int
    to_age_days: int
    interval_days: int
    weight_velocity_g_per_day: float | None
    velocity_status: str                 # below_range | within_range | above_range | not_assessed
    velocity_reason: str | None
    weight_loss: bool
    delta_z: dict                        # {"waz": float|None, "haz": ..., "whz": ...}
    delta_z_per_month: dict
    flags: tuple[str, ...]               # subset of: weight, linear, wasting
    new_below: dict                      # {"waz": "-2"|"-3"|None, ...}


@dataclass(frozen=True)
class LongitudinalResult:
    visits_used: int
    visits_excluded: tuple[dict, ...]
    intervals: tuple[IntervalGrowth, ...]
    weight_faltering: str                # none | possible | sustained | not_assessable
    linear_faltering: str
    wasting_faltering: str
    growth_faltering: bool               # any of the three at possible or sustained
    level: str                           # none | possible | sustained | not_assessable
    cumulative: dict
    reasons: tuple[str, ...]
    config: FalteringConfig
    advisory: str = ADVISORY


def _z(panel: IndicatorPanel, code: str):
    return getattr(panel, code).z


def _new_below(z0, z1):
    if z0 is None or z1 is None:
        return None
    return "-3" if z0 >= -3 > z1 else "-2" if z0 >= -2 > z1 else None


def _kind_level(flags_per_interval: list[bool], n_assessed: int, sustained: int, cum: bool) -> str:
    if n_assessed == 0:
        return "not_assessable"
    run = best = 0
    for f in flags_per_interval:
        run = run + 1 if f else 0
        best = max(best, run)
    if best >= sustained:
        return "sustained"
    return "possible" if (best >= 1 or cum) else "none"


def analyse_growth(record: ChildRecord, config: FalteringConfig | None = None) -> LongitudinalResult:
    cfg = config or FalteringConfig()
    panels: list[tuple[int, IndicatorPanel]] = []
    excluded: list[dict] = []
    for v in record.visits:
        try:
            p = compute_panel(record.sex, v)
        except InputError as exc:
            excluded.append({"age_days": v.age_days, "reason": f"invalid_measurement: {exc}"})
            continue
        if p.any_implausible:
            excluded.append({"age_days": v.age_days, "reason": "implausible_measurement_recheck"})
            continue
        panels.append((v.age_days, p))
    weights = {v.age_days: v.weight_kg for v in record.visits}

    intervals: list[IntervalGrowth] = []
    reasons: list[str] = []
    for (a0, p0), (a1, p1) in zip(panels, panels[1:]):
        gap = a1 - a0
        if gap < cfg.min_interval_days:
            reasons.append(f"interval_too_short_{a0}_{a1}")
            continue
        if gap > cfg.max_interval_days:
            reasons.append(f"interval_too_long_{a0}_{a1}")
            continue
        try:
            g = assess_weight_velocity(record.sex, a0, weights[a0], a1, weights[a1])
        except ValueError:
            continue
        months = gap / DAYS_PER_MONTH
        dz, dzm, newb = {}, {}, {}
        for code in ("waz", "haz", "whz"):
            z0, z1 = _z(p0, code), _z(p1, code)
            dz[code] = None if z0 is None or z1 is None else round(z1 - z0, 2)
            dzm[code] = None if dz[code] is None else round(dz[code] / months, 3)
            newb[code] = _new_below(z0, z1)
        flags = []
        if g.flagged or (dz["waz"] is not None and dz["waz"] <= -cfg.fall_sd):
            flags.append("weight")
        if (dz["haz"] is not None and dz["haz"] <= -cfg.fall_sd) or newb["haz"]:
            flags.append("linear")
        if (dz["whz"] is not None and dz["whz"] <= -cfg.fall_sd) or newb["whz"]:
            flags.append("wasting")
        intervals.append(IntervalGrowth(
            a0, a1, gap, g.rate_g_per_day, "not_assessed" if not g.assessed else g.status, g.reason, g.weight_loss,
            dz, dzm, tuple(flags), newb))

    # cumulative fall from the best value inside the window, latest panel vs earlier panels
    cumulative = {}
    if panels:
        last_age, last = panels[-1]
        for code in ("waz", "haz", "whz"):
            zl = _z(last, code)
            prior = [_z(p, code) for a, p in panels[:-1] if last_age - a <= cfg.cumulative_window_days and _z(p, code) is not None]
            fall = None if zl is None or not prior else round(zl - max(prior), 2)
            cumulative[code] = {"fall_sd": fall, "flagged": fall is not None and fall <= -cfg.fall_sd}

    levels = {}
    for kind, code in (("weight", "waz"), ("linear", "haz"), ("wasting", "whz")):
        per = [kind in i.flags for i in intervals]
        levels[kind] = _kind_level(per, len(intervals), cfg.sustained_intervals, cumulative.get(code, {}).get("flagged", False))
    if len(panels) < 2:
        reasons.append("fewer_than_two_usable_visits")
    order = {"not_assessable": 0, "none": 1, "possible": 2, "sustained": 3}
    overall = max(levels.values(), key=order.__getitem__)
    return LongitudinalResult(
        len(panels), tuple(excluded), tuple(intervals), levels["weight"], levels["linear"], levels["wasting"],
        overall in ("possible", "sustained"), overall, cumulative, tuple(reasons), cfg)
