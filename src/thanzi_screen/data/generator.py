"""Seeded synthetic generation. WHO tables are inverted to make measurements, and labels
come from the real Phase 1 and Phase 2 engine on the recorded values."""
from __future__ import annotations

import math
import random

from ..anthro import InputError, compute_anthropometry, sd_value
from ..anthro import tables
from ..rules import Appetite, Complication, DangerSign, OedemaGrade, classify
from .config import GenConfig
from .noise import DAYS_PER_MONTH, inject
from .review import review_reasons
from .schema import COLUMNS, enc_bool, enc_set, row_to_inputs
from .splits import assign_splits

LENGTH_MAX_AGE_DAYS = 730
MAX_AGE_DAYS = 1856


def _inv_plain(lms, z):
    l, m, s = lms
    return sd_value(m, l, s, z)


def _inv_adjusted(lms, z):
    """Inverse of the WHO adjusted z-score for weight-based indicators."""
    l, m, s = lms
    if z > 3:
        sd3 = sd_value(m, l, s, 3)
        return sd3 + (z - 3) * (sd3 - sd_value(m, l, s, 2))
    if z < -3:
        sd3n = sd_value(m, l, s, -3)
        return sd3n + (z + 3) * (sd_value(m, l, s, -2) - sd3n)
    return sd_value(m, l, s, z)


def _position(age_days: int) -> str:
    return "length" if age_days <= LENGTH_MAX_AGE_DAYS else "height"


def _wflh_lms(sex: str, age_days: int, length: float):
    name = "wfl" if age_days <= LENGTH_MAX_AGE_DAYS else "wfh"
    return tables.lenhei_table(name, sex).lookup(length)


def _draw_anthropometry(rng, cfg, sex, age_days):
    lhfa_lms = tables.age_table("lhfa", sex)[age_days]
    for _ in range(200):
        zh = max(-5.9, min(5.9, rng.gauss(cfg.lhfa_mean, cfg.lhfa_sd)))
        length = round(_inv_plain(lhfa_lms, zh), 1)
        lms = _wflh_lms(sex, age_days, length)
        if lms is None:
            continue
        e = rng.gauss(0, 1)
        rho = cfg.hw_corr
        zw = cfg.wflh_mean + cfg.wflh_sd * (rho * (zh - cfg.lhfa_mean) / cfg.lhfa_sd + math.sqrt(1 - rho ** 2) * e)
        zw = max(-4.9, min(4.9, zw))
        weight = round(_inv_adjusted(lms, zw), 2)
        if weight > 0:
            return zh, length, zw, weight
    raise RuntimeError("could not draw a measurable child")


def _clinical(rng, cfg, age_days, sam, muac_true):
    infant = age_days / DAYS_PER_MONTH < 6
    appetite = Appetite.FAILED if rng.random() < (cfg.appetite_fail_sam if sam else cfg.appetite_fail_other) else Appetite.PASSED
    signs = frozenset({rng.choice(list(DangerSign))}) if rng.random() < (cfg.danger_sam if sam else cfg.danger_other) else frozenset()
    comps = frozenset({rng.choice(list(Complication))}) if rng.random() < (cfg.compl_sam if sam else cfg.compl_other) else frozenset()
    well = not (DangerSign.LETHARGY_NOT_ALERT in signs or DangerSign.UNCONSCIOUSNESS in signs)
    hiv = None if rng.random() < cfg.hiv_unknown else (rng.random() < cfg.hiv_positive)
    inf = [rng.random() < p for p in (cfg.infant_visible_wasting, cfg.infant_too_weak, cfg.infant_no_gain)] if infant else [None] * 3
    # MCAR missingness
    muac = muac_true
    if muac is not None and rng.random() < cfg.missing_muac:
        muac = None
    if rng.random() < cfg.missing_appetite:
        appetite = Appetite.NOT_DONE
    if rng.random() < cfg.missing_danger:
        signs = None
    if rng.random() < cfg.missing_compl:
        comps = None
    if rng.random() < cfg.missing_well_alert:
        well = None
    if infant:
        inf = [None if rng.random() < cfg.missing_infant_items else v for v in inf]
    return muac, dict(appetite=appetite.value, danger_signs=enc_set(signs), complications=enc_set(comps),
                      clinically_well_and_alert=enc_bool(well), hiv_positive=enc_bool(hiv),
                      visible_severe_wasting=enc_bool(inf[0], na=not infant),
                      too_weak_to_suckle=enc_bool(inf[1], na=not infant),
                      failure_to_gain_weight=enc_bool(inf[2], na=not infant))


def _engine_columns(row: dict, cfg: GenConfig) -> None:
    try:
        a = compute_anthropometry(
            sex=row["sex"], weight_kg=row["weight_kg"], length_height_cm=row["length_height_cm"],
            measure_position=row["measure_position"], age_days=row["age_days"], oedema=row["oedema"] != "none")
        r = classify(a, row_to_inputs(row))
    except InputError:
        row.update(wfa_z=None, lhfa_z=None, wflh_z=None, cmam_class="INPUT_ERROR", tier="recheck",
                   programme="", rules_fired="", review_needed=True, review_reasons="input_error")
        return
    reasons = review_reasons(a, r, row["muac_cm"], row["oedema"] != "none", cfg)
    row.update(wfa_z=a.wfa.z, lhfa_z=a.lhfa.z, wflh_z=a.wflh.z, cmam_class=r.classification.value,
               tier=r.tier.value, programme=r.programme or "", rules_fired=";".join(r.rules_fired),
               review_needed=bool(reasons), review_reasons=";".join(reasons))


def _row(child_id, record_type, district, sex, truth, recorded, clinical, oedema, error, cfg) -> dict:
    row = dict(
        child_id=child_id, is_synthetic=True, record_type=record_type, split="", district=district, sex=sex,
        age_days=recorded["age_days"], measure_position=_position(truth["age_days"]),
        weight_kg=recorded["weight_kg"], length_height_cm=recorded["length_height_cm"], muac_cm=recorded["muac_cm"],
        oedema=oedema, **clinical,
        true_age_days=truth["age_days"], true_weight_kg=truth["weight_kg"], true_length_height_cm=truth["length_height_cm"],
        true_muac_cm=truth["muac_cm"], true_lhfa_z=truth["lhfa_z"], true_wflh_z=truth["wflh_z"], injected_error=error)
    _engine_columns(row, cfg)
    return row


def _new_id(rng, used: set) -> str:
    while True:
        cid = f"syn-{rng.getrandbits(40):010x}"
        if cid not in used:
            used.add(cid)
            return cid


def _random_record(rng, cfg, used) -> dict:
    sex = rng.choice(("male", "female"))
    district = rng.choice(cfg.districts)
    age = rng.randint(0, MAX_AGE_DAYS)
    zh, length, zw, weight = _draw_anthropometry(rng, cfg, sex, age)
    oedema = "none"
    if rng.random() < cfg.p_oedema:
        oedema = rng.choices((OedemaGrade.PLUS.value, OedemaGrade.PLUS_PLUS.value, OedemaGrade.PLUS_PLUS_PLUS.value),
                             cfg.oedema_grade_weights)[0]
    muac_true = None
    if age / DAYS_PER_MONTH >= 6:
        muac_true = max(5.0, round(cfg.muac_at_z0_cm + cfg.muac_per_z_cm * zw + rng.gauss(0, cfg.muac_sd_cm), 1))
    sam = oedema != "none" or zw < -3 or (muac_true is not None and muac_true < 11.5)
    muac_obs, clinical = _clinical(rng, cfg, age, sam, muac_true)
    truth = dict(age_days=age, weight_kg=weight, length_height_cm=length, muac_cm=muac_true, lhfa_z=zh, wflh_z=zw)
    recorded, error = inject(rng, cfg, dict(age_days=age, weight_kg=weight, length_height_cm=length, muac_cm=muac_obs))
    return _row(_new_id(rng, used), "random", district, sex, truth, recorded, clinical, oedema, error, cfg)


def _full_clinical(age_days: int) -> dict:
    infant = age_days / DAYS_PER_MONTH < 6
    return dict(appetite="passed", danger_signs="none", complications="none", clinically_well_and_alert="true",
                hiv_positive="false", visible_severe_wasting=enc_bool(False, na=not infant),
                too_weak_to_suckle=enc_bool(False, na=not infant), failure_to_gain_weight=enc_bool(False, na=not infant))


def _boundary_records(rng, cfg, used) -> list[dict]:
    """Deterministic records at each Phase 2 threshold. Recorded values equal truth."""
    specs = []
    for muac in (11.4, 11.5, 12.4, 12.5):
        specs.append(dict(age=365, muac=muac, zw=0.0))
    for z in (-3.01, -3.0, -2.01, -2.0):
        specs.append(dict(age=365, muac=None, zw=z))
    for age in (182, 183):
        specs.append(dict(age=age, muac=11.0, zw=0.0))
    for w in (2.99, 3.0, 3.01):
        specs.append(dict(age=243, muac=13.0, weight=w, length=55.0))
    for grade in ("+", "++", "+++"):
        specs.append(dict(age=365, muac=13.0, zw=0.0, oedema=grade))
    out = []
    for sp in specs:
        sex = "male"
        age = sp["age"]
        if "weight" in sp:
            length, weight, zh, zw = sp["length"], sp["weight"], 0.0, 0.0
        else:
            zh = 0.0
            length = round(_inv_plain(tables.age_table("lhfa", sex)[age], zh), 1)
            weight = round(_inv_adjusted(_wflh_lms(sex, age, length), sp["zw"]), 2)
            zw = sp["zw"]
        muac = sp["muac"] if age / DAYS_PER_MONTH >= 6 else sp["muac"]  # supplied on purpose below 6 months, to test the ignore rule
        truth = dict(age_days=age, weight_kg=weight, length_height_cm=length, muac_cm=muac, lhfa_z=zh, wflh_z=zw)
        out.append(_row(_new_id(rng, used), "boundary", cfg.districts[0], sex, truth, dict(truth), _full_clinical(age),
                        sp.get("oedema", "none"), "none", cfg))
    return out


def generate(cfg: GenConfig) -> list[dict]:
    """50,000 random records (cfg.n) followed by the boundary set. Deterministic for a given config."""
    rng = random.Random(cfg.seed)
    used: set = set()
    rows = [_random_record(rng, cfg, used) for _ in range(cfg.n)]
    rows += _boundary_records(rng, cfg, used)
    assign_splits(rows, cfg.split_fractions, cfg.seed)
    return rows
