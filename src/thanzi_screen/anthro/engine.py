"""Anthropometric calculation engine (Phase 1).

Computes WHO z-scores only. It does not classify; classification is Phase 2.
Documented behaviours follow the WHO Child Growth Standards and WHO igrowup/anthro
implementation (docs/references/register.md, R6). Decision log: D10-D14.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import Enum

from . import tables
from .lms import zscore_adjusted, zscore_plain

DAYS_PER_MONTH = 30.4375
MAX_AGE_DAYS = 1856  # last day before 61 completed months (WHO)
LENGTH_MAX_AGE_DAYS = 730  # <731 days: recumbent length; >=731: standing height
LENHEI_OFFSET_CM = 0.7

FLAG_ADJUSTED = "adjusted_beyond_3sd"
FLAG_IMPLAUSIBLE = "implausible_recheck_measurements"
WARN_CONVERTED = "length_height_converted_by_0.7cm_to_age_convention"

# WHO flag limits (lower, upper) on the computed z-score (register R6)
_PLAUSIBLE = {"wfa": (-6.0, 5.0), "lhfa": (-6.0, 6.0), "wfl": (-5.0, 5.0), "wfh": (-5.0, 5.0)}


class Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"


class MeasurePosition(str, Enum):
    LENGTH = "length"  # recumbent
    HEIGHT = "height"  # standing


class InputError(ValueError):
    """Malformed or inconsistent input."""


@dataclass(frozen=True)
class IndicatorResult:
    indicator: str
    status: str  # "ok" | "not_computable"
    z: float | None = None
    z_unadjusted: float | None = None
    reason: str | None = None
    flags: tuple[str, ...] = ()
    table: str | None = None


@dataclass(frozen=True)
class AnthropometryResult:
    age_days: int
    age_months: float
    length_height_used_cm: float
    wfa: IndicatorResult
    lhfa: IndicatorResult
    wflh: IndicatorResult
    warnings: tuple[str, ...] = ()
    weight_kg: float | None = None  # validated input weight, used by Phase 2 (CMAM Table 5 weight criterion)


def _positive(name: str, v: object) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise InputError(f"{name} must be a positive finite number")
    return float(v)


def age_in_days(date_of_birth: date, measurement_date: date) -> int:
    days = (measurement_date - date_of_birth).days
    if days < 0:
        raise InputError("measurement_date is before date_of_birth")
    return days


def _nc(indicator: str, reason: str) -> IndicatorResult:
    return IndicatorResult(indicator, "not_computable", reason=reason)


def _finish(indicator: str, table: str, y: float, lms, adjust: bool) -> IndicatorResult:
    l, m, s = lms
    plain = zscore_plain(y, m, l, s)
    z = zscore_adjusted(y, m, l, s) if adjust else plain
    flags = []
    if adjust and abs(plain) > 3:
        flags.append(FLAG_ADJUSTED)
    lo, hi = _PLAUSIBLE[indicator]
    if z < lo or z > hi:
        flags.append(FLAG_IMPLAUSIBLE)
    return IndicatorResult(indicator, "ok", z=z, z_unadjusted=plain, flags=tuple(flags), table=table)


def compute_anthropometry(
    *,
    sex: Sex | str,
    weight_kg: float,
    length_height_cm: float,
    measure_position: MeasurePosition | str,
    age_days: int | None = None,
    date_of_birth: date | None = None,
    measurement_date: date | None = None,
    oedema: bool = False,
) -> AnthropometryResult:
    try:
        sex = Sex(sex)
        position = MeasurePosition(measure_position)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    weight = _positive("weight_kg", weight_kg)
    lenhei = _positive("length_height_cm", length_height_cm)

    if age_days is not None:
        if date_of_birth is not None or measurement_date is not None:
            raise InputError("give age_days or both dates, not both")
        if isinstance(age_days, bool) or not isinstance(age_days, int) or age_days < 0:
            raise InputError("age_days must be a non-negative integer")
        days = age_days
    elif date_of_birth is not None and measurement_date is not None:
        days = age_in_days(date_of_birth, measurement_date)
    else:
        raise InputError("age_days or both date_of_birth and measurement_date required")

    months = days / DAYS_PER_MONTH
    out_of_range = days > MAX_AGE_DAYS

    # Convert to the age convention (length <731 days, height otherwise), as WHO does
    warnings: list[str] = []
    used = lenhei
    if days <= LENGTH_MAX_AGE_DAYS and position is MeasurePosition.HEIGHT:
        used = lenhei + LENHEI_OFFSET_CM
        warnings.append(WARN_CONVERTED)
    elif days > LENGTH_MAX_AGE_DAYS and position is MeasurePosition.LENGTH:
        used = lenhei - LENHEI_OFFSET_CM
        warnings.append(WARN_CONVERTED)
    used = round(used, 6)

    sx = sex.value
    wflh_name = "wfl" if days <= LENGTH_MAX_AGE_DAYS else "wfh"

    if out_of_range:
        r = "age_out_of_range_0_1856_days"
        return AnthropometryResult(days, months, used, _nc("wfa", r), _nc("lhfa", r), _nc(wflh_name, r), tuple(warnings), weight_kg=weight)

    # height/length-for-age: plain LMS (WHO does not adjust it)
    lhfa = _finish("lhfa", f"lhfa_{'boys' if sx == 'male' else 'girls'}.csv", used, tables.age_table("lhfa", sx)[days], adjust=False)

    if oedema:
        # WHO: weight-based z-scores are not calculated when oedema is present
        r = "oedema_weight_unreliable"
        return AnthropometryResult(days, months, used, _nc("wfa", r), lhfa, _nc(wflh_name, r), tuple(warnings), weight_kg=weight)

    wfa = _finish("wfa", f"wfa_{'boys' if sx == 'male' else 'girls'}.csv", weight, tables.age_table("wfa", sx)[days], adjust=True)

    tbl = tables.lenhei_table(wflh_name, sx)
    lms = tbl.lookup(used)
    if lms is None:
        wflh = _nc(wflh_name, f"{wflh_name}_out_of_table_range_{tbl.min:g}_{tbl.max:g}_cm")
    else:
        wflh = _finish(wflh_name, f"{wflh_name}_{'boys' if sx == 'male' else 'girls'}.csv", weight, lms, adjust=True)
    return AnthropometryResult(days, months, used, wfa, lhfa, wflh, tuple(warnings), weight_kg=weight)
