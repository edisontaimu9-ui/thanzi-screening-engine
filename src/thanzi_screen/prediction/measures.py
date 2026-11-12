"""WHO measures for one observation, computed once and cached. Shared by the labels and the features."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ..anthro import InputError, compute_anthropometry
from ..anthro.engine import FLAG_IMPLAUSIBLE
from ..factors import Visit
from ..rules import OedemaGrade

MUAC_MIN_MONTHS = 6.0


@dataclass(frozen=True)
class Measures:
    age_days: int
    age_months: float
    usable: bool                  # z-scores could be computed and no plausibility flag was raised
    waz: float | None
    haz: float | None
    whz: float | None
    muac_cm: float | None         # None under 6 months or not measured
    oedema: bool
    weight_kg: float


@lru_cache(maxsize=200_000)
def measures(sex: str, visit: Visit) -> Measures:
    oedema = visit.oedema is not OedemaGrade.NONE
    months = visit.age_days / 30.4375
    muac = visit.muac_cm if months >= MUAC_MIN_MONTHS else None
    try:
        a = compute_anthropometry(sex=sex, weight_kg=visit.weight_kg, length_height_cm=visit.length_height_cm,
                                  measure_position=visit.measure_position, age_days=visit.age_days, oedema=oedema)
    except InputError:
        return Measures(visit.age_days, months, False, None, None, None, muac, oedema, visit.weight_kg)
    inds = (a.wfa, a.lhfa, a.wflh)
    if any(i.status == "ok" and FLAG_IMPLAUSIBLE in i.flags for i in inds):
        return Measures(visit.age_days, a.age_months, False, None, None, None, muac, oedema, visit.weight_kg)

    def z(i):
        return round(i.z, 4) if i.status == "ok" and i.z is not None else None

    usable = a.lhfa.status == "ok"
    return Measures(visit.age_days, a.age_months, usable, z(a.wfa), z(a.lhfa), z(a.wflh), muac, oedema, visit.weight_kg)
