"""Factor groups for one child: anthropometric visits, demographic, clinical, feeding, maternal and socioeconomic.

Rules shared by every field:
- None means not assessed. It is never read as "normal" or "absent". An empty collection means assessed, none present.
- No identifiers. No names, dates of birth, contacts, fine geography or facility names. Age is in whole days.
- Ranges here only reject values that cannot be real. Clinical plausibility of measurements is the WHO engine's job.
- HIV status is deliberately not a factor here: it is sensitive and is not needed by either module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from enum import Enum

from ..rules import Appetite, Complication, DangerSign, OedemaGrade


class FactorError(ValueError):
    """A value cannot be real (wrong type, out of range, inconsistent)."""


def _num(name: str, v, lo: float, hi: float, allow_none: bool = True):
    if v is None:
        if allow_none:
            return None
        raise FactorError(f"{name} is required")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise FactorError(f"{name} must be a finite number")
    if not lo <= v <= hi:
        raise FactorError(f"{name} must be between {lo:g} and {hi:g}")
    return float(v)


def _int(name: str, v, lo: int, hi: int):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int):
        raise FactorError(f"{name} must be a whole number")
    if not lo <= v <= hi:
        raise FactorError(f"{name} must be between {lo} and {hi}")
    return v


def _bool(name: str, v):
    if v is not None and not isinstance(v, bool):
        raise FactorError(f"{name} must be true, false or not assessed")
    return v


def _choice(name: str, v, allowed: tuple):
    if v is not None and v not in allowed:
        raise FactorError(f"{name} must be one of: {', '.join(allowed)}")
    return v


class Residence(str, Enum):
    URBAN = "urban"
    RURAL = "rural"


@dataclass(frozen=True)
class Visit:
    """One measurement visit: anthropometry plus the clinical findings recorded at that visit."""
    age_days: int
    weight_kg: float
    length_height_cm: float
    measure_position: str                        # "length" (lying) or "height" (standing)
    muac_cm: float | None = None                 # 6 to 59 months only
    oedema: OedemaGrade = OedemaGrade.NONE       # required: never assumed absent
    appetite: Appetite = Appetite.NOT_DONE
    danger_signs: frozenset[DangerSign] | None = None
    complications: frozenset[Complication] | None = None
    clinically_well_and_alert: bool | None = None
    hc_cm: float | None = None

    def __post_init__(self):
        _int("age_days", self.age_days, 0, 1856 * 2)
        if self.age_days is None:
            raise FactorError("age_days is required")
        _num("weight_kg", self.weight_kg, 0.3, 40.0, allow_none=False)
        _num("length_height_cm", self.length_height_cm, 20.0, 150.0, allow_none=False)
        if self.measure_position not in ("length", "height"):
            raise FactorError("measure_position must be length or height")
        _num("muac_cm", self.muac_cm, 3.0, 40.0)
        _num("hc_cm", self.hc_cm, 15.0, 70.0)
        _bool("clinically_well_and_alert", self.clinically_well_and_alert)


@dataclass(frozen=True)
class Demographic:
    residence: Residence | None = None
    birth_weight_g: float | None = None
    gestational_age_weeks: float | None = None
    multiple_birth: bool | None = None
    birth_interval_months: float | None = None   # months since the mother's previous birth; None for a first birth or unknown
    birth_order: int | None = None

    def __post_init__(self):
        _num("birth_weight_g", self.birth_weight_g, 300.0, 6500.0)
        _num("gestational_age_weeks", self.gestational_age_weeks, 22.0, 44.0)
        _bool("multiple_birth", self.multiple_birth)
        _num("birth_interval_months", self.birth_interval_months, 0.0, 240.0)
        _int("birth_order", self.birth_order, 1, 25)


@dataclass(frozen=True)
class Clinical:
    """Recent history. Windows are the two weeks before the visit unless stated."""
    diarrhoea_2wk: bool | None = None
    fever_2wk: bool | None = None
    cough_or_fast_breathing_2wk: bool | None = None
    malaria_recent: bool | None = None           # confirmed or treated in the last month
    fully_immunised_for_age: bool | None = None
    vitamin_a_last_6mo: bool | None = None
    deworming_last_6mo: bool | None = None       # for children 12 months and older
    previous_acute_malnutrition_episode: bool | None = None
    hospital_admission_last_6mo: bool | None = None

    def __post_init__(self):
        for f in fields(self):
            _bool(f.name, getattr(self, f.name))


@dataclass(frozen=True)
class Feeding:
    exclusive_breastfeeding_to_6mo: bool | None = None   # asked of children 6 months and older
    currently_breastfed: bool | None = None
    complementary_start_age_months: float | None = None
    food_groups_24h: int | None = None                   # 0 to 8 WHO/UNICEF food groups eaten in the last 24 hours
    meals_24h: int | None = None                         # meals and snacks in the last 24 hours, excluding milk feeds
    breastmilk_substitute_use: bool | None = None

    def __post_init__(self):
        _bool("exclusive_breastfeeding_to_6mo", self.exclusive_breastfeeding_to_6mo)
        _bool("currently_breastfed", self.currently_breastfed)
        _num("complementary_start_age_months", self.complementary_start_age_months, 0.0, 59.0)
        _int("food_groups_24h", self.food_groups_24h, 0, 8)
        _int("meals_24h", self.meals_24h, 0, 12)
        _bool("breastmilk_substitute_use", self.breastmilk_substitute_use)


@dataclass(frozen=True)
class Maternal:
    age_years: float | None = None
    education: str | None = None                 # none | primary | secondary | higher
    muac_cm: float | None = None                 # mother's MUAC
    antenatal_visits: int | None = None
    mother_is_primary_caregiver: bool | None = None

    def __post_init__(self):
        _num("mother age_years", self.age_years, 12.0, 60.0)
        _choice("education", self.education, ("none", "primary", "secondary", "higher"))
        _num("mother muac_cm", self.muac_cm, 10.0, 50.0)
        _int("antenatal_visits", self.antenatal_visits, 0, 30)
        _bool("mother_is_primary_caregiver", self.mother_is_primary_caregiver)


@dataclass(frozen=True)
class Socioeconomic:
    wealth_quintile: int | None = None           # 1 poorest to 5 richest, as defined by the data source
    household_size: int | None = None
    improved_water: bool | None = None
    improved_sanitation: bool | None = None
    food_insecure: bool | None = None            # the data source's own definition: record it in the dataset manifest
    receives_cash_or_food_support: bool | None = None

    def __post_init__(self):
        _int("wealth_quintile", self.wealth_quintile, 1, 5)
        _int("household_size", self.household_size, 1, 40)
        for n in ("improved_water", "improved_sanitation", "food_insecure", "receives_cash_or_food_support"):
            _bool(n, getattr(self, n))


FACTOR_GROUPS = ("demographic", "clinical", "feeding", "maternal", "socioeconomic")


@dataclass(frozen=True)
class ChildRecord:
    """A child: sex, the visits so far (any order, sorted on use) and the static factor groups."""
    sex: str
    visits: tuple[Visit, ...]
    demographic: Demographic = field(default_factory=Demographic)
    clinical: Clinical = field(default_factory=Clinical)
    feeding: Feeding = field(default_factory=Feeding)
    maternal: Maternal = field(default_factory=Maternal)
    socioeconomic: Socioeconomic = field(default_factory=Socioeconomic)

    def __post_init__(self):
        if self.sex not in ("male", "female"):
            raise FactorError("sex must be male or female")
        if not self.visits:
            raise FactorError("at least one visit is required")
        ordered = tuple(sorted(self.visits, key=lambda v: v.age_days))
        ages = [v.age_days for v in ordered]
        if len(set(ages)) != len(ages):
            raise FactorError("two visits have the same age_days")
        object.__setattr__(self, "visits", ordered)

    @property
    def latest(self) -> Visit:
        return self.visits[-1]


def completeness(record: ChildRecord) -> dict:
    """Share of each factor group that was assessed. Reporting only: it is never used to fill a gap.

    A group with nothing assessed is listed as such; it is not scored as normal."""
    out = {}
    for name in FACTOR_GROUPS:
        group = getattr(record, name)
        values = [getattr(group, f.name) for f in fields(group)]
        known = sum(v is not None for v in values)
        out[name] = {"assessed": known, "total": len(values), "fraction": round(known / len(values), 2),
                     "status": "none_assessed" if known == 0 else "partial" if known < len(values) else "complete"}
    return out
