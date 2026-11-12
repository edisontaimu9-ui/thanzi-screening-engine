"""Feature engineering for seven groups: anthropometric, longitudinal growth, demographic, clinical, feeding, maternal,
socioeconomic.

Leak-free by construction: `build_features(child, index)` reads only observations up to and including `index` (tested by
changing every later observation). The CMAM classification, tier and referral are NOT features, and neither are
cut-off flags derived from them. Values are continuous or plain 0/1. Never identifiers, district, period or any label.
A missing input stays None. Imputation and missing-value indicators belong to the preprocessor, fitted on training data.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..rules import Appetite
from .measures import Measures, measures
from .records import Child

GROUPS = ("anthropometric", "longitudinal", "demographic", "clinical", "feeding", "maternal", "socioeconomic")
MIN_PREV_GAP_DAYS = 14
WINDOW_DAYS = 180


@dataclass(frozen=True)
class FeatureSpec:
    group: str
    kind: str                 # continuous | binary | count
    monotone: int = 0         # +1 higher value never lowers risk, -1 never raises it, 0 unconstrained
    note: str = ""


def _s(group, kind, monotone=0, note=""):
    return FeatureSpec(group, kind, monotone, note)


FEATURES: dict[str, FeatureSpec] = {
    # anthropometric, at the index visit
    "age_months": _s("anthropometric", "continuous"), "sex_male": _s("anthropometric", "binary"),
    "waz": _s("anthropometric", "continuous", -1), "haz": _s("anthropometric", "continuous", -1),
    "whz": _s("anthropometric", "continuous", -1), "muac_cm": _s("anthropometric", "continuous", -1),
    "oedema_present": _s("anthropometric", "binary", 1),
    # longitudinal growth, from earlier visits and the index visit
    "n_prior_visits": _s("longitudinal", "count"), "days_since_prev": _s("longitudinal", "continuous"),
    "d_waz": _s("longitudinal", "continuous", -1), "d_haz": _s("longitudinal", "continuous", -1),
    "d_whz": _s("longitudinal", "continuous", -1), "d_muac_cm": _s("longitudinal", "continuous", -1),
    "weight_velocity_g_day": _s("longitudinal", "continuous", -1),
    "whz_slope_per_month_3": _s("longitudinal", "continuous", -1),
    "min_prior_whz": _s("longitudinal", "continuous"), "min_prior_waz": _s("longitudinal", "continuous"),
    "min_prior_muac_cm": _s("longitudinal", "continuous"),
    "waz_fall_from_max_180d": _s("longitudinal", "continuous", -1),
    # demographic and birth
    "residence_rural": _s("demographic", "binary"), "birth_weight_kg": _s("demographic", "continuous"),
    "low_birth_weight": _s("demographic", "binary"), "gestational_age_weeks": _s("demographic", "continuous"),
    "preterm": _s("demographic", "binary"), "multiple_birth": _s("demographic", "binary"),
    "birth_interval_months": _s("demographic", "continuous"), "birth_interval_lt24": _s("demographic", "binary"),
    "birth_order": _s("demographic", "count"),
    # clinical: findings at the visit, then recent history
    "appetite_failed": _s("clinical", "binary", 1), "appetite_not_done": _s("clinical", "binary"),
    "danger_sign_count": _s("clinical", "count", 1), "danger_unknown": _s("clinical", "binary"),
    "complication_count": _s("clinical", "count", 1), "compl_unknown": _s("clinical", "binary"),
    "diarrhoea_2wk": _s("clinical", "binary"), "fever_2wk": _s("clinical", "binary"),
    "cough_or_fast_breathing_2wk": _s("clinical", "binary"), "malaria_recent": _s("clinical", "binary"),
    "fully_immunised_for_age": _s("clinical", "binary"), "vitamin_a_last_6mo": _s("clinical", "binary"),
    "deworming_last_6mo": _s("clinical", "binary"),
    "previous_acute_malnutrition_episode": _s("clinical", "binary"),
    "hospital_admission_last_6mo": _s("clinical", "binary"),
    # feeding
    "exclusive_breastfeeding_to_6mo": _s("feeding", "binary"), "currently_breastfed": _s("feeding", "binary"),
    "complementary_start_age_months": _s("feeding", "continuous"), "food_groups_24h": _s("feeding", "count"),
    "dietary_diversity_ge5": _s("feeding", "binary"), "meals_24h": _s("feeding", "count"),
    "breastmilk_substitute_use": _s("feeding", "binary"),
    # maternal
    "mother_age_years": _s("maternal", "continuous"), "teen_mother": _s("maternal", "binary"),
    "mother_education_level": _s("maternal", "count", note="0 none, 1 primary, 2 secondary, 3 higher"),
    "mother_muac_cm": _s("maternal", "continuous"), "antenatal_visits": _s("maternal", "count"),
    "mother_is_primary_caregiver": _s("maternal", "binary"),
    # socioeconomic
    "wealth_quintile": _s("socioeconomic", "count"), "household_size": _s("socioeconomic", "count"),
    "improved_water": _s("socioeconomic", "binary"), "improved_sanitation": _s("socioeconomic", "binary"),
    "wash_score": _s("socioeconomic", "count", note="improved water plus improved sanitation, when both are known"),
    "food_insecure": _s("socioeconomic", "binary"), "receives_cash_or_food_support": _s("socioeconomic", "binary"),
}
FEATURE_NAMES = tuple(FEATURES)
MONOTONE = {n: s.monotone for n, s in FEATURES.items() if s.monotone}
FORBIDDEN_PARTS = ("future", "label", "outcome", "child_id", "district", "period", "cmam", "tier", "class", "referral",
                    "split", "true_", "injected", "review")
EDUCATION = {"none": 0, "primary": 1, "secondary": 2, "higher": 3}


def _b(v):
    return None if v is None else float(v)


def _slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope of z against age in months. Needs three points and a span."""
    if len(points) < 3:
        return None
    n = len(points)
    mx, my = sum(p[0] for p in points) / n, sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    if sxx <= 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in points) / sxx


def _delta(a, b):
    return None if a is None or b is None else a - b


def build_features(child: Child, index: int) -> dict[str, float | None]:
    """Features for the observation at `index`, from observations 0..index only."""
    obs = child.observations[: index + 1]
    cur_o = obs[-1]
    v = cur_o.visit
    m = measures(child.sex, v)
    prior = [(o, measures(child.sex, o.visit)) for o in obs[:-1]]
    prior_ok = [(o, p) for o, p in prior if p.usable]
    f: dict[str, float | None] = {
        "age_months": m.age_months, "sex_male": float(child.sex == "male"),
        "waz": m.waz, "haz": m.haz, "whz": m.whz, "muac_cm": m.muac_cm, "oedema_present": float(m.oedema),
    }
    # longitudinal
    f["n_prior_visits"] = float(len(prior_ok))
    prev = next(((o, p) for o, p in reversed(prior_ok) if m.age_days - p.age_days >= MIN_PREV_GAP_DAYS), None)
    for k in ("days_since_prev", "d_waz", "d_haz", "d_whz", "d_muac_cm", "weight_velocity_g_day"):
        f[k] = None
    if prev is not None:
        _, p = prev
        gap = m.age_days - p.age_days
        f["days_since_prev"] = float(gap)
        f["d_waz"], f["d_haz"], f["d_whz"] = _delta(m.waz, p.waz), _delta(m.haz, p.haz), _delta(m.whz, p.whz)
        f["d_muac_cm"] = _delta(m.muac_cm, p.muac_cm)
        f["weight_velocity_g_day"] = (m.weight_kg - p.weight_kg) * 1000.0 / gap
    pts = [(p.age_months, p.whz) for _, p in prior_ok if p.whz is not None][-2:]
    if m.whz is not None:
        pts.append((m.age_months, m.whz))
    f["whz_slope_per_month_3"] = _slope(pts) if len(pts) == 3 else None
    for key, attr in (("min_prior_whz", "whz"), ("min_prior_waz", "waz"), ("min_prior_muac_cm", "muac_cm")):
        vals = [getattr(p, attr) for _, p in prior_ok if getattr(p, attr) is not None]
        f[key] = min(vals) if vals else None
    recent = [p.waz for _, p in prior_ok if p.waz is not None and m.age_days - p.age_days <= WINDOW_DAYS]
    f["waz_fall_from_max_180d"] = _delta(m.waz, max(recent)) if recent and m.waz is not None else None
    # demographic
    d = child.demographic
    f["residence_rural"] = None if d.residence is None else float(d.residence.value == "rural")
    f["birth_weight_kg"] = None if d.birth_weight_g is None else d.birth_weight_g / 1000.0
    f["low_birth_weight"] = None if d.birth_weight_g is None else float(d.birth_weight_g < 2500)
    f["gestational_age_weeks"] = d.gestational_age_weeks
    f["preterm"] = None if d.gestational_age_weeks is None else float(d.gestational_age_weeks < 37)
    f["multiple_birth"] = _b(d.multiple_birth)
    f["birth_interval_months"] = d.birth_interval_months
    f["birth_interval_lt24"] = None if d.birth_interval_months is None else float(d.birth_interval_months < 24)
    f["birth_order"] = None if d.birth_order is None else float(d.birth_order)
    # clinical
    f["appetite_failed"] = float(v.appetite is Appetite.FAILED)
    f["appetite_not_done"] = float(v.appetite is Appetite.NOT_DONE)
    f["danger_sign_count"] = float(len(v.danger_signs or ()))
    f["danger_unknown"] = float(v.danger_signs is None)
    f["complication_count"] = float(len(v.complications or ()))
    f["compl_unknown"] = float(v.complications is None)
    c = cur_o.clinical
    for k in ("diarrhoea_2wk", "fever_2wk", "cough_or_fast_breathing_2wk", "malaria_recent", "fully_immunised_for_age",
              "vitamin_a_last_6mo", "deworming_last_6mo", "previous_acute_malnutrition_episode",
              "hospital_admission_last_6mo"):
        f[k] = _b(getattr(c, k))
    # feeding
    fd = cur_o.feeding
    f["exclusive_breastfeeding_to_6mo"] = _b(fd.exclusive_breastfeeding_to_6mo)
    f["currently_breastfed"] = _b(fd.currently_breastfed)
    f["complementary_start_age_months"] = fd.complementary_start_age_months
    f["food_groups_24h"] = None if fd.food_groups_24h is None else float(fd.food_groups_24h)
    f["dietary_diversity_ge5"] = None if fd.food_groups_24h is None else float(fd.food_groups_24h >= 5)
    f["meals_24h"] = None if fd.meals_24h is None else float(fd.meals_24h)
    f["breastmilk_substitute_use"] = _b(fd.breastmilk_substitute_use)
    # maternal
    mt = child.maternal
    f["mother_age_years"] = mt.age_years
    f["teen_mother"] = None if mt.age_years is None else float(mt.age_years < 20)
    f["mother_education_level"] = None if mt.education is None else float(EDUCATION[mt.education])
    f["mother_muac_cm"] = mt.muac_cm
    f["antenatal_visits"] = None if mt.antenatal_visits is None else float(mt.antenatal_visits)
    f["mother_is_primary_caregiver"] = _b(mt.mother_is_primary_caregiver)
    # socioeconomic
    s = child.socioeconomic
    f["wealth_quintile"] = None if s.wealth_quintile is None else float(s.wealth_quintile)
    f["household_size"] = None if s.household_size is None else float(s.household_size)
    f["improved_water"], f["improved_sanitation"] = _b(s.improved_water), _b(s.improved_sanitation)
    f["wash_score"] = (None if s.improved_water is None or s.improved_sanitation is None
                       else float(s.improved_water) + float(s.improved_sanitation))
    f["food_insecure"] = _b(s.food_insecure)
    f["receives_cash_or_food_support"] = _b(s.receives_cash_or_food_support)
    return {n: f[n] for n in FEATURE_NAMES}
