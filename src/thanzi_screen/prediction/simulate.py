"""SIMULATED longitudinal children, to build and test the prediction pipeline before real data arrives.

NOT CLINICAL. Every association below is an ASSUMPTION written into this file, not an estimate from any data. A model
trained on this data can only learn these assumptions, so its accuracy says nothing about real children. Outcomes are not
drawn from a formula: they follow from simulated growth trajectories (latent WHO z-scores that are then turned into
weights, lengths and MUAC with the WHO reference tables), so labels are built exactly as they would be from real visits.

Realism that is on purpose: irregular visit gaps, loss to follow-up that is more likely for poorer households, missing
factor values that are more likely for poorer households, measurement noise, rare oedema. Deterministic: the same seed
gives the same children.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..anthro import tables
from ..anthro.lms import sd_value
from ..factors import Clinical, Demographic, Feeding, Maternal, Socioeconomic, Visit
from ..factors.schema import Residence
from ..rules import Appetite, Complication, DangerSign, OedemaGrade
from .records import Child, Observation

DISTRICTS = tuple(f"D{i:02d}" for i in range(1, 9))     # neutral codes: no real district rates are implied
MAX_AGE_DAYS = 1850

# ASSUMED effects (placeholders, not estimates).
A = {
    "poverty_to_whz_mean": -0.40, "frailty_to_whz_mean": -0.25, "illness_hit": 0.7, "low_diet_drift": -0.18,
    "poverty_to_haz_mean": -0.45, "ar_whz": 0.7, "ar_haz": 0.96, "whz_noise": 0.30, "haz_noise": 0.12,
    "p_oedema_severe": 0.05, "p_oedema_other": 0.002,
}


@dataclass(frozen=True)
class SimConfig:
    n_children: int = 3000
    seed: int = 20260101
    max_visits: int = 9
    missing_rate: float = 0.08           # base chance a factor value is not assessed (higher for poorer households)


def _clip(v, lo, hi):
    return max(lo, min(hi, v))


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


def _miss(rng, p, v):
    return None if rng.random() < p else v


def _statics(rng: random.Random, cfg: SimConfig):
    quint = rng.choices((1, 2, 3, 4, 5), weights=(30, 25, 20, 15, 10))[0]
    rural = rng.random() < (0.93 if quint <= 2 else 0.75)
    pm = cfg.missing_rate * (1.6 if quint <= 2 else 1.0)
    food_insecure = rng.random() < (0.55 if quint <= 2 else 0.25 if quint == 3 else 0.1)
    water = rng.random() < 0.45 + 0.1 * quint
    sanit = rng.random() < 0.25 + 0.12 * quint
    support = rng.random() < (0.2 if quint <= 2 else 0.05)
    mage = _clip(rng.gauss(26, 6), 15, 46)
    edu = rng.choices(("none", "primary", "secondary", "higher"), weights=(18 - 2 * quint, 50, 25 + 3 * quint, 4 + quint))[0]
    mmuac = _clip(rng.gauss(25.3 - (1.2 if food_insecure else 0), 2.6), 17, 38)
    preterm = rng.random() < 0.10
    ga = round(rng.uniform(30, 36.9), 1) if preterm else round(_clip(rng.gauss(39.2, 1.2), 37, 43), 1)
    bw = _clip(rng.gauss(3050, 430) - (450 if preterm else 0) - (60 if quint <= 2 else 0), 900, 5200)
    first = rng.random() < 0.25
    interval = None if first else round(_clip(rng.lognormvariate(math.log(32), 0.45), 10, 120), 0)
    demo = Demographic(Residence.RURAL if rural else Residence.URBAN, _miss(rng, pm, round(bw, -1)), _miss(rng, pm, ga),
                       rng.random() < 0.03, interval, 1 if first else rng.randint(2, 8))
    mat = Maternal(_miss(rng, pm, round(mage, 0)), _miss(rng, pm, edu), _miss(rng, pm * 1.5, round(mmuac, 1)),
                   _miss(rng, pm, (max(0, min(12, int(rng.gauss(4.0, 1.8)))) if rng.random() < 0.97 else 0)),
                   _miss(rng, pm, rng.random() < 0.9))
    socio = Socioeconomic(quint, _miss(rng, pm, rng.randint(3, 10)), _miss(rng, pm, water), _miss(rng, pm, sanit),
                          _miss(rng, pm * 1.5, food_insecure), _miss(rng, pm, support))
    risk = (3 - quint) * 0.5 + (0.6 if food_insecure else 0) + (0.3 if not water else 0) + (0.3 if not sanit else 0) \
        + (0.5 if preterm else 0) + (0.4 if bw < 2500 else 0) + (0.2 if mmuac < 23 else 0)
    return demo, mat, socio, quint, pm, risk, food_insecure


def _length_weight(sex: str, age_days: int, haz: float, whz: float, rng: random.Random):
    l, m, s = tables.age_table("lhfa", sex)[age_days]
    length = round(sd_value(m, l, s, haz) + rng.gauss(0, 0.25), 1)
    name = "wfl" if age_days <= 730 else "wfh"
    tbl = tables.lenhei_table(name, sex)
    length = round(_clip(length, tbl.min + 0.1, tbl.max - 0.1), 1)
    wl, wm, ws = tbl.lookup(length)
    weight = round(sd_value(wm, wl, ws, whz) * (1 + rng.gauss(0, 0.008)), 2)
    return length, weight


def simulate_child(index: int, cfg: SimConfig) -> Child:
    rng = random.Random(f"{cfg.seed}:{index}")
    sex = rng.choice(("male", "female"))
    district = rng.choice(DISTRICTS)
    demo, mat, socio, quint, pm, risk, food_insecure = _statics(rng, cfg)
    frailty = rng.gauss(0, 1)
    whz_mean = -0.25 + A["poverty_to_whz_mean"] * risk * 0.5 + A["frailty_to_whz_mean"] * frailty
    haz_mean = -0.7 + A["poverty_to_haz_mean"] * risk * 0.6 + 0.0 * frailty
    age = rng.randint(183, 36 * 30)
    whz = whz_mean + rng.gauss(0, 0.7)
    haz = haz_mean - 0.01 * (age / 30) + rng.gauss(0, 0.5)
    period_start = rng.randint(0, 17)
    day_offset = 0
    obs: list[Observation] = []
    prev_illness = False
    for k in range(cfg.max_visits):
        if age > MAX_AGE_DAYS:
            break
        illness_p = _clip(0.12 + 0.07 * risk + (0.05 if age < 730 else 0), 0.03, 0.7)
        diarrhoea, fever, cough = (rng.random() < illness_p * w for w in (0.8, 0.9, 1.0))
        ill = diarrhoea or fever or cough
        groups = int(_clip(round(rng.gauss(3.4 + 0.4 * (quint - 3) - (0.7 if food_insecure else 0), 1.3)), 0, 8))
        if k > 0:
            drift = (-A["illness_hit"] if prev_illness else 0.0) + (A["low_diet_drift"] if groups < 4 else 0.04)
            whz = whz_mean + A["ar_whz"] * (whz - whz_mean) + drift * 0.6 + rng.gauss(0, A["whz_noise"])
            haz = haz_mean + A["ar_haz"] * (haz - haz_mean) - 0.012 * (gap / 30 if age < 730 else gap / 90) \
                + rng.gauss(0, A["haz_noise"])
        whz, haz = _clip(whz, -4.6, 3.0), _clip(haz, -5.0, 3.0)
        length, weight = _length_weight(sex, age, haz, whz, rng)
        months = age / 30.4375
        muac = None
        if months >= 6 and rng.random() > 0.03:
            muac = round(_clip(14.3 + 0.85 * whz + 0.15 * haz + rng.gauss(0, 0.4), 8.5, 20.0), 1)
        p_oed = A["p_oedema_severe"] if whz < -3 else A["p_oedema_other"]
        oed = OedemaGrade.NONE
        if rng.random() < p_oed:
            oed = rng.choices((OedemaGrade.PLUS, OedemaGrade.PLUS_PLUS, OedemaGrade.PLUS_PLUS_PLUS), weights=(6, 3, 1))[0]
        app = Appetite.NOT_DONE if rng.random() < 0.15 else (
            Appetite.FAILED if rng.random() < 0.02 + 0.3 * _sigmoid(-2.5 * (whz + 2.8)) else Appetite.PASSED)
        signs = frozenset(s for s in DangerSign if rng.random() < (0.004 + (0.03 if ill else 0) + 0.02 * (whz < -3)))
        comps = set(c for c in Complication if rng.random() < 0.003 + 0.01 * ill)
        if diarrhoea and rng.random() < 0.3:
            comps.add(Complication.DIARRHOEA)
        visit = Visit(age, weight, length, "length" if age <= 730 else "height", muac_cm=muac, oedema=oed, appetite=app,
                      danger_signs=_miss(rng, pm, signs), complications=_miss(rng, pm, frozenset(comps)))
        pv = pm
        clin = Clinical(_miss(rng, pv, diarrhoea), _miss(rng, pv, fever), _miss(rng, pv, cough),
                        _miss(rng, pv, rng.random() < 0.08 + 0.1 * fever), _miss(rng, pv, rng.random() < 0.8 - 0.05 * risk),
                        _miss(rng, pv, rng.random() < 0.7), _miss(rng, pv, rng.random() < 0.5) if months >= 12 else None,
                        _miss(rng, pv, rng.random() < 0.06 + 0.04 * (whz < -1.5)), _miss(rng, pv, rng.random() < 0.05 + 0.1 * ill))
        feed = Feeding(_miss(rng, pv, rng.random() < 0.6) if months >= 6 else None,
                       _miss(rng, pv, rng.random() < (0.9 if months < 18 else 0.55)),
                       _miss(rng, pv, round(_clip(rng.gauss(5.5, 1.2), 2, 12), 1)), _miss(rng, pv, groups),
                       _miss(rng, pv, int(_clip(round(rng.gauss(2.4 + 0.15 * groups, 0.9)), 0, 6))),
                       _miss(rng, pv, rng.random() < 0.1))
        y, mth = divmod(period_start + day_offset // 30, 12)
        obs.append(Observation(visit, clin, feed, f"{2024 + y}-{mth + 1:02d}"))
        prev_illness = ill
        # next visit: irregular gap, and loss to follow-up that is more likely for poorer households
        if rng.random() < _clip(0.12 + 0.05 * risk, 0.05, 0.4):
            break
        gap = int(_clip(rng.lognormvariate(math.log(52), 0.5), 21, 200))
        age += gap
        day_offset += gap
    return Child(f"c{index:06d}", sex, tuple(obs), demo, mat, socio, district)


def simulate_children(cfg: SimConfig | None = None) -> list[Child]:
    cfg = cfg or SimConfig()
    return [simulate_child(i, cfg) for i in range(cfg.n_children)]
