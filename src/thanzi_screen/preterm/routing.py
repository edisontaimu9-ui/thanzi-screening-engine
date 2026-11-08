"""Which engine screens a baby, and with what age. Pure functions, standard library only.

Rules (config in routing_config.json and preterm_rules.json):
- Born under 37 weeks or under 2500 g, and post-menstrual age (PMA) under 50 weeks: preterm engine.
- PMA 50 weeks or more: under-5 engine on corrected age (chronological age - (40 - GA) weeks) while the baby is
  preterm (GA under 37) and younger than the configured chronological age (36 months if GA under 32 weeks).
- Otherwise the under-5 engine on chronological age, exactly as before.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from ..anthro import InputError
from ..rules import Tier
from . import engine as _engine

_DIR = Path(__file__).parent
CONFIG = json.loads((_DIR / "routing_config.json").read_text(encoding="utf-8"))
DAYS_PER_MONTH = 30.4375            # same constant as the under-5 engine

PATH_UNDER5 = "under5"
PATH_PRETERM = "preterm"
PATH_CORRECTED = "under5_corrected_age"

LEVEL_MAP: dict[str, str] = {k: v for k, v in CONFIG["level_map"].items() if not k.startswith("_")}
if set(LEVEL_MAP) != set(_engine.LEVELS) or not set(LEVEL_MAP.values()) <= {t.value for t in Tier}:
    raise RuntimeError("routing_config.json level_map must cover exactly the preterm levels and use existing under-5 tiers")


def tier_for(level: str) -> str:
    """The one place a preterm referral level becomes an under-5 tier."""
    return LEVEL_MAP[level]


def at_least(level: str, minimum: str) -> str:
    order = _engine.LEVELS
    return order[max(order.index(level), order.index(minimum))]


@dataclass(frozen=True)
class Route:
    path: str
    reason: str
    age_days: int                       # chronological
    age_days_used: int                  # what the engine that runs will be given
    ga_weeks: float | None
    birth_weight_g: float | None
    pma_weeks: float | None
    preterm_birth: bool                 # GA under 37 weeks
    low_birth_weight: bool              # under 2500 g
    corrected_age_days: int | None
    corrected_age_until_months: int | None
    notes: tuple[str, ...] = ()

    @property
    def has_birth_context(self) -> bool:
        return self.ga_weeks is not None or self.birth_weight_g is not None


def _finite_positive(name: str, v: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise InputError(f"{name} must be a positive finite number")
    return float(v)


def corrected_age_days(age_days: int, ga_weeks: float) -> int:
    """Chronological age minus the weeks missing from 40, in whole days (half a day rounds up)."""
    behind = (CONFIG["corrected_age"]["full_term_weeks"] - ga_weeks) * 7
    return age_days - math.floor(behind + 0.5)


def corrected_age_until_months(ga_weeks: float) -> int | None:
    c = CONFIG["corrected_age"]
    if ga_weeks >= c["applies_when_ga_weeks_below"]:
        return None
    for tier in c["use_until_chronological_months"]:
        if ga_weeks < tier["ga_weeks_below"]:
            return tier["months"]
    return None


def route(age_days: int, ga_weeks: float | None = None, birth_weight_g: float | None = None) -> Route:
    """Decide the path. Raises InputError for impossible or incomplete preterm input."""
    if isinstance(age_days, bool) or not isinstance(age_days, int) or age_days < 0:
        raise InputError("age_days must not be negative")
    cfg = CONFIG["route_to_preterm"]
    if ga_weeks is not None:
        ga_weeks = _finite_positive("gestational_age_weeks", ga_weeks)
        lo, hi = CONFIG["plausible_ga_weeks"]["min"], CONFIG["plausible_ga_weeks"]["max"]
        if not lo <= ga_weeks <= hi:
            raise InputError("gestational_age_weeks is outside the supported range")
    if birth_weight_g is not None:
        birth_weight_g = _finite_positive("birth_weight_g", birth_weight_g)
        w = CONFIG["plausible_weights"]["birth_weight_g"]
        if not w["min"] <= birth_weight_g <= w["max"]:
            raise InputError("birth_weight_g is outside the supported range, give grams")

    preterm = ga_weeks is not None and ga_weeks < cfg["ga_weeks_below"]
    lbw = birth_weight_g is not None and birth_weight_g < cfg["birth_weight_g_below"]
    pma = None if ga_weeks is None else round(ga_weeks + age_days / 7, 2)

    def make(path, reason, used, corrected=None, until=None, notes=()):
        return Route(path, reason, age_days, used, ga_weeks, birth_weight_g, pma, preterm, lbw, corrected, until, tuple(notes))

    if not (preterm or lbw):
        return make(PATH_UNDER5, "not_preterm_or_low_birth_weight", age_days)
    if ga_weeks is None:
        # Born under 2500 g but gestational age unknown: Fenton and corrected age both need it.
        return make(PATH_UNDER5, "gestational_age_unknown", age_days, notes=("gestational_age_missing_for_low_birth_weight",))

    handover = _engine.R["hand_over_to_under5_engine"]["at_pma_weeks"]
    if pma < handover:
        if birth_weight_g is None:
            raise InputError("birth_weight_g is required for a baby born under 37 weeks")
        return make(PATH_PRETERM, "preterm_or_low_birth_weight_below_handover_pma", age_days)

    until = corrected_age_until_months(ga_weeks)
    if until is not None and age_days / DAYS_PER_MONTH < until:
        corrected = corrected_age_days(age_days, ga_weeks)
        return make(PATH_CORRECTED, "pma_at_or_after_handover_corrected_age", corrected, corrected, until)
    return make(PATH_UNDER5, "pma_at_or_after_handover_chronological_age", age_days,
                notes=("corrected_age_period_over" if preterm else "term_low_birth_weight_chronological_age",))
