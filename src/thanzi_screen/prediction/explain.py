"""Explanations for one prediction: exact per-feature contributions and short plain-language drivers. Standard library only.

Contributions are exact for these models: baseline + sum(contributions) equals the model's raw output (a logit for logistic
regression and gradient boosting, a probability for the random forest). A feature's value column and its "not recorded" flag are
added together, so a gap that raises the estimate is shown as "not recorded", never hidden. Contributions are in the units of the
RAW model; calibration is a monotone rescaling, so the order of the drivers does not change.

Drivers shown to a health worker are only features that RAISE the estimate (escalate-only, like the model itself). They say what
contributed to the number, never that a feature caused the outcome. The full audit list is for reviewers, not for the bedside.
"""
from __future__ import annotations

from .features import FEATURES
from .model import PredictionModel

MAX_DRIVERS = 3
NOT_SHOWN = frozenset({"sex_male"})      # kept in the audit list; not offered as a bedside "reason"

# name: (text when the value is 1, text when 0 or None). A None means the feature is not offered as a driver in that state.
_BINARY = {
    "oedema_present": ("bilateral pitting oedema", None), "residence_rural": ("rural residence", None),
    "low_birth_weight": ("low birth weight", None), "preterm": ("born preterm", None), "multiple_birth": ("twin or multiple birth", None),
    "birth_interval_lt24": ("less than 24 months since the previous birth", None),
    "appetite_failed": ("appetite test failed", None), "appetite_not_done": ("appetite test not done", None),
    "danger_unknown": ("danger signs not checked", None), "compl_unknown": ("complications not checked", None),
    "diarrhoea_2wk": ("diarrhoea in the last 2 weeks", None), "fever_2wk": ("fever in the last 2 weeks", None),
    "cough_or_fast_breathing_2wk": ("cough or fast breathing in the last 2 weeks", None),
    "malaria_recent": ("recent malaria", None),
    "fully_immunised_for_age": (None, "not fully immunised for age"), "vitamin_a_last_6mo": (None, "no vitamin A in the last 6 months"),
    "deworming_last_6mo": (None, "no deworming in the last 6 months"),
    "previous_acute_malnutrition_episode": ("a previous episode of acute malnutrition", None),
    "hospital_admission_last_6mo": ("a hospital admission in the last 6 months", None),
    "exclusive_breastfeeding_to_6mo": (None, "not exclusively breastfed to 6 months"),
    "currently_breastfed": (None, "not currently breastfed"),
    "dietary_diversity_ge5": (None, "fewer than 5 food groups in the last 24 hours"),
    "breastmilk_substitute_use": ("breastmilk substitute in use", None), "teen_mother": ("mother under 20", None),
    "mother_is_primary_caregiver": (None, "mother is not the main caregiver"),
    "improved_water": (None, "no improved water source"), "improved_sanitation": (None, "no improved sanitation"),
    "food_insecure": ("household food insecurity", None), "receives_cash_or_food_support": (None, "no cash or food support"),
}
# name: (label, format) for continuous and count features
_NUMERIC = {
    "age_months": ("age", "{:.0f} months"), "waz": ("weight-for-age z-score", "{:.1f}"), "haz": ("height-for-age z-score", "{:.1f}"),
    "whz": ("weight-for-height z-score", "{:.1f}"), "muac_cm": ("MUAC", "{:.1f} cm"),
    "n_prior_visits": ("number of earlier visits", "{:.0f}"), "days_since_prev": ("days since the previous visit", "{:.0f}"),
    "d_waz": ("change in weight-for-age z-score", "{:+.1f}"), "d_haz": ("change in height-for-age z-score", "{:+.1f}"),
    "d_whz": ("change in weight-for-height z-score", "{:+.1f}"), "d_muac_cm": ("change in MUAC", "{:+.1f} cm"),
    "weight_velocity_g_day": ("weight gain", "{:.1f} g per day"), "whz_slope_per_month_3": ("weight-for-height trend", "{:+.2f} z per month"),
    "min_prior_whz": ("lowest earlier weight-for-height z-score", "{:.1f}"), "min_prior_waz": ("lowest earlier weight-for-age z-score", "{:.1f}"),
    "min_prior_muac_cm": ("lowest earlier MUAC", "{:.1f} cm"), "waz_fall_from_max_180d": ("fall in weight-for-age z-score over 6 months", "{:+.1f}"),
    "birth_weight_kg": ("birth weight", "{:.1f} kg"), "gestational_age_weeks": ("gestational age", "{:.0f} weeks"),
    "birth_interval_months": ("months since the previous birth", "{:.0f}"), "birth_order": ("birth order", "{:.0f}"),
    "danger_sign_count": ("danger signs", "{:.0f}"), "complication_count": ("complications", "{:.0f}"),
    "complementary_start_age_months": ("age complementary foods started", "{:.0f} months"),
    "food_groups_24h": ("food groups in 24 hours", "{:.0f}"), "meals_24h": ("meals in 24 hours", "{:.0f}"),
    "mother_age_years": ("mother's age", "{:.0f} years"), "mother_education_level": ("mother's education level", "{:.0f} (0 none, 3 higher)"),
    "mother_muac_cm": ("mother's MUAC", "{:.1f} cm"), "antenatal_visits": ("antenatal visits", "{:.0f}"),
    "wealth_quintile": ("household wealth quintile", "{:.0f}"), "household_size": ("household size", "{:.0f}"),
    "wash_score": ("water and sanitation score", "{:.0f} of 2"),
}


def feature_of(column: str) -> str:
    return column[:-len("_missing")] if column.endswith("_missing") and column[:-len("_missing")] in FEATURES else column


def phrase(name: str, value) -> str | None:
    """Plain-language text for one feature at this value, or None when it is not something to show a health worker."""
    if name in NOT_SHOWN:
        return None
    if value is None:
        label = _NUMERIC[name][0] if name in _NUMERIC else name.replace("_", " ")
        return f"{label}: not recorded"
    if name in _BINARY:
        one, zero = _BINARY[name]
        return one if value >= 0.5 else zero
    if name in _NUMERIC:
        label, fmt = _NUMERIC[name]
        return f"{label} {fmt.format(value)}"
    return None


def explain(model: PredictionModel, x: list[float], features: dict) -> tuple[list[dict], dict]:
    """(drivers, audit). Drivers: up to MAX_DRIVERS features that raise the estimate, strongest first. Audit: every feature."""
    base, phi, unit = model.contributions(x)
    per: dict[str, float] = {}
    for col, c in zip(model.columns, phi):
        per[feature_of(col)] = per.get(feature_of(col), 0.0) + c
    order = sorted(per, key=lambda n: (-per[n], n))
    drivers = []
    for n in order:
        if per[n] <= 0 or len(drivers) == MAX_DRIVERS:
            break
        text = phrase(n, features.get(n))
        if text:
            drivers.append({"feature": n, "text": text, "direction": "raises"})
    audit = {"unit": unit, "baseline": round(base, 6),
             "contributions": [{"feature": n, "value": features.get(n), "contribution": round(per[n], 6)}
                               for n in sorted(per, key=lambda k: (-abs(per[k]), k))]}
    return drivers, audit
