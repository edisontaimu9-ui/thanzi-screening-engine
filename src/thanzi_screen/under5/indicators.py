"""One visit turned into the WHO growth indicators, the MUAC category and the oedema finding.

WAZ, HAZ and WHZ come from the WHO Child Growth Standards engine in thanzi_screen.anthro (adjusted method beyond
+/-3 SD, weight-based z-scores withheld when oedema is present). MUAC is categorised with the cut-offs of the CMAM
Guidelines, Malawi, 2016 (the same constants the rules use). MUAC-for-age z-scores are NOT computed: the WHO MUAC-for-age
tables are not among this repository's checksummed reference tables, and no values are invented.

A value that cannot be computed is reported as not assessable with a reason. It is never read as normal.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..anthro import InputError, compute_anthropometry
from ..anthro.engine import FLAG_IMPLAUSIBLE
from ..factors import Visit
from ..rules import OedemaGrade
from ..rules import rules_v2016 as R

MUAC_MIN_MONTHS = float(R.CHILD_PATHWAY_MIN_MONTHS)

# Status of one WHO indicator (WHO cut-offs: below -2 SD moderate, below -3 SD severe).
SEVERE, MODERATE, NORMAL, ABOVE_2, ABOVE_3, NOT_ASSESSABLE = (
    "severe", "moderate", "normal", "above_plus2", "above_plus3", "not_assessable")
NAMES = {"waz": "underweight", "haz": "stunting", "whz": "wasting"}


@dataclass(frozen=True)
class IndicatorValue:
    code: str                    # waz | haz | whz
    condition: str               # underweight | stunting | wasting
    z: float | None
    status: str                  # severe | moderate | normal | above_plus2 | above_plus3 | not_assessable
    reason: str | None = None    # why not assessable
    implausible: bool = False    # WHO plausibility flag: recheck the measurement
    adjusted_beyond_3sd: bool = False


@dataclass(frozen=True)
class MuacFinding:
    muac_cm: float | None
    category: str                # severe | moderate | normal | not_measured | not_applicable_under_6_months
    cutoffs_cm: tuple[float, float] = (R.MUAC_SEVERE_CM, R.MUAC_MODERATE_CM)
    z_for_age: None = None       # deliberately absent, see module docstring


@dataclass(frozen=True)
class OedemaFinding:
    grade: str                   # none | + | ++ | +++
    present: bool
    bilateral_pitting_severe: bool   # +++ : grade the CMAM rules treat as the most severe
    weight_indicators_withheld: bool


@dataclass(frozen=True)
class IndicatorPanel:
    age_days: int
    age_months: float
    waz: IndicatorValue
    haz: IndicatorValue
    whz: IndicatorValue
    muac: MuacFinding
    oedema: OedemaFinding
    wasting_and_stunting: bool | None     # concurrent: both below -2 SD. None when either is not assessable
    any_implausible: bool
    warnings: tuple[str, ...]


def _status(z: float | None, upper: bool) -> str:
    if z is None:
        return NOT_ASSESSABLE
    if z < -3:
        return SEVERE
    if z < -2:
        return MODERATE
    if upper and z > 3:
        return ABOVE_3
    if upper and z > 2:
        return ABOVE_2
    return NORMAL


def _value(code: str, ind, upper: bool) -> IndicatorValue:
    cond = NAMES[code]
    if ind.status != "ok" or ind.z is None:
        return IndicatorValue(code, cond, None, NOT_ASSESSABLE, ind.reason)
    return IndicatorValue(code, cond, round(ind.z, 2), _status(ind.z, upper), None, FLAG_IMPLAUSIBLE in ind.flags,
                          "adjusted_beyond_3sd" in ind.flags)


def _muac(visit: Visit, months: float) -> MuacFinding:
    if months < MUAC_MIN_MONTHS:
        return MuacFinding(None, "not_applicable_under_6_months")
    if visit.muac_cm is None:
        return MuacFinding(None, "not_measured")
    m = visit.muac_cm
    cat = "severe" if m < R.MUAC_SEVERE_CM else "moderate" if m < R.MUAC_MODERATE_CM else "normal"
    return MuacFinding(m, cat)


def compute_panel(sex: str, visit: Visit) -> IndicatorPanel:
    """Indicator panel for one visit. Raises InputError when the measurements cannot be turned into z-scores at all."""
    oedema = visit.oedema is not OedemaGrade.NONE
    a = compute_anthropometry(sex=sex, weight_kg=visit.weight_kg, length_height_cm=visit.length_height_cm,
                              measure_position=visit.measure_position, age_days=visit.age_days, oedema=oedema)
    waz, haz, whz = _value("waz", a.wfa, True), _value("haz", a.lhfa, False), _value("whz", a.wflh, True)
    both = None if NOT_ASSESSABLE in (haz.status, whz.status) else (
        haz.status in (SEVERE, MODERATE) and whz.status in (SEVERE, MODERATE))
    return IndicatorPanel(
        a.age_days, round(a.age_months, 2), waz, haz, whz, _muac(visit, a.age_months),
        OedemaFinding(visit.oedema.value, oedema, visit.oedema is OedemaGrade.PLUS_PLUS_PLUS, oedema),
        both, any(v.implausible for v in (waz, haz, whz)), tuple(a.warnings))


__all__ = ["IndicatorPanel", "IndicatorValue", "InputError", "MuacFinding", "OedemaFinding", "compute_panel"]
