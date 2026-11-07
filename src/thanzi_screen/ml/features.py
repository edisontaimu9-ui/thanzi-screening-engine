"""Leak-free features. Only information available at the point of care is used:
recorded values, Phase 1 z-scores and flags, and Phase 2 outputs. Never true_*, injected_error,
review_*, split, record_type or child_id."""
from __future__ import annotations

from ..anthro import InputError, compute_anthropometry
from ..rules import ClinicalInputs, OedemaGrade, classify

DAYS_PER_MONTH = 30.4375
IMPLAUSIBLE = "implausible_recheck_measurements"
FORBIDDEN_FEATURE_PARTS = ("true_", "injected", "review", "split", "record_type", "child_id")

FEATURES = (
    "age_months", "sex_male", "position_height", "weight_kg", "length_height_cm",
    "muac_cm", "muac_missing", "muac_ge_30", "muac_unit_suspect",
    "wfa_z", "lhfa_z", "wflh_z", "wfa_missing", "lhfa_missing", "wflh_missing",
    "implaus_wfa", "implaus_lhfa", "implaus_wflh", "implaus_count",
    "abs_wfa_minus_wflh", "abs_wfa_minus_lhfa", "abs_wflh_minus_lhfa",
    "length_swap_lhfa_gain", "length_swap_wflh_gain", "weight_div10_abs_wflh", "weight_mul10_abs_wflh",
    "age_dist_6m_days", "age_heap_exact",
    "is_sam", "is_mam", "is_unable", "oedema_present",
    "appetite_not_done", "danger_unknown", "compl_unknown", "well_unknown",
)
FIELDS = ("weight", "length_height", "muac", "age")
ERROR_TO_FIELD = {"weight_decimal_shift": "weight", "length_digit_transposition": "length_height",
                  "muac_unit_error": "muac", "age_heaping": "age"}


def _clip(z, lim=10.0):
    return max(-lim, min(lim, z))


def _z(ind):
    return None if ind.status != "ok" or ind.z is None else _clip(ind.z)


def _swap_digits(length: float) -> float:
    whole = int(length)
    s = str(whole)
    if len(s) < 2 or s[-1] == s[-2]:
        return length
    return round(int(s[:-2] + s[-1] + s[-2]) + (length - whole), 1)


def _anthro(sex, age_days, weight, length, position, oedema):
    try:
        return compute_anthropometry(sex=sex, weight_kg=weight, length_height_cm=length,
                                     measure_position=position, age_days=age_days, oedema=oedema)
    except InputError:
        return None


def features_from_inputs(sex: str, age_days: int, weight_kg: float, length_height_cm: float,
                         measure_position: str, clinical: ClinicalInputs):
    """Return (feature dict, AnthropometryResult, ClassificationResult). Raises InputError on invalid input."""
    oedema = clinical.oedema != OedemaGrade.NONE
    a = compute_anthropometry(sex=sex, weight_kg=weight_kg, length_height_cm=length_height_cm,
                              measure_position=measure_position, age_days=age_days, oedema=oedema)
    r = classify(a, clinical)
    wfa, lhfa, wflh = _z(a.wfa), _z(a.lhfa), _z(a.wflh)
    f: dict[str, float] = {
        "age_months": a.age_months, "sex_male": float(sex == "male"), "position_height": float(measure_position == "height"),
        "weight_kg": weight_kg, "length_height_cm": length_height_cm,
    }
    muac = clinical.muac_cm
    f["muac_cm"] = 0.0 if muac is None else muac
    f["muac_missing"] = float(muac is None)
    f["muac_ge_30"] = float(muac is not None and muac >= 30)
    f["muac_unit_suspect"] = float(muac is not None and muac >= 50 and 5 <= muac / 10 <= 30)
    for name, z in (("wfa", wfa), ("lhfa", lhfa), ("wflh", wflh)):
        f[f"{name}_z"] = 0.0 if z is None else z
        f[f"{name}_missing"] = float(z is None)
    flags = [float(i.status == "ok" and IMPLAUSIBLE in i.flags) for i in (a.wfa, a.lhfa, a.wflh)]
    f["implaus_wfa"], f["implaus_lhfa"], f["implaus_wflh"] = flags
    f["implaus_count"] = sum(flags)
    f["abs_wfa_minus_wflh"] = 0.0 if wfa is None or wflh is None else abs(wfa - wflh)
    f["abs_wfa_minus_lhfa"] = 0.0 if wfa is None or lhfa is None else abs(wfa - lhfa)
    f["abs_wflh_minus_lhfa"] = 0.0 if wflh is None or lhfa is None else abs(wflh - lhfa)
    # Would a common recording slip make the values more plausible?
    swapped = _swap_digits(length_height_cm)
    s_lhfa = s_wflh = None
    if swapped != length_height_cm:
        sa = _anthro(sex, age_days, weight_kg, swapped, measure_position, oedema)
        if sa is not None:
            s_lhfa, s_wflh = _z(sa.lhfa), _z(sa.wflh)
    f["length_swap_lhfa_gain"] = 0.0 if s_lhfa is None or lhfa is None else abs(lhfa) - abs(s_lhfa)
    f["length_swap_wflh_gain"] = 0.0 if s_wflh is None or wflh is None else abs(wflh) - abs(s_wflh)
    for key, w in (("weight_div10_abs_wflh", weight_kg / 10), ("weight_mul10_abs_wflh", weight_kg * 10)):
        wa = _anthro(sex, age_days, round(w, 2), length_height_cm, measure_position, oedema) if w > 0 else None
        z = None if wa is None else _z(wa.wflh)
        f[key] = 10.0 if z is None else abs(z)
    unit = 6 * DAYS_PER_MONTH
    nearest = round(age_days / unit) * unit
    f["age_dist_6m_days"] = abs(age_days - nearest)
    f["age_heap_exact"] = float(f["age_dist_6m_days"] <= 0.5)
    cls = r.classification.value
    f["is_sam"] = float(cls.startswith("SAM"))
    f["is_mam"] = float(cls == "MAM")
    f["is_unable"] = float(cls == "UNABLE_TO_CLASSIFY")
    f["oedema_present"] = float(oedema)
    f["appetite_not_done"] = float(clinical.appetite.value == "not_done")
    f["danger_unknown"] = float(clinical.danger_signs is None)
    f["compl_unknown"] = float(clinical.complications is None)
    f["well_unknown"] = float(clinical.clinically_well_and_alert is None)
    return f, a, r


def vector(f: dict) -> list[float]:
    return [float(f[n]) for n in FEATURES]


def row_inputs(row: dict):
    """Recorded-only inputs from a dataset row (strings or python types)."""
    from ..data.schema import row_to_inputs
    return (row["sex"], int(row["age_days"]), float(row["weight_kg"]), float(row["length_height_cm"]),
            row["measure_position"], row_to_inputs(row))
