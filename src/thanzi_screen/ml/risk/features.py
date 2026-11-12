"""Features for the clinical risk model (advisory). Same function at training time and at request time.

Independent of the rules: the CMAM classification is NOT a feature, so the model is a second opinion and cannot
simply learn the cut-offs. Only values available at the point of care are used. Never identifiers, district, date or
outcome. A child is scored only when every input the model needs is present and plausible: nothing is imputed as
normal (a missing MUAC means "not scored", never "average MUAC").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...anthro import InputError
from ...rules import ClinicalInputs, OedemaGrade
from ..features import features_from_inputs

RISK_FEATURES = (
    "age_months", "sex_male", "wfa_z", "lhfa_z", "wflh_z", "muac_cm",
    "oedema_present", "appetite_failed", "appetite_not_done",
    "danger_sign_count", "danger_unknown", "complication_count", "compl_unknown",
    "has_previous", "weight_rate_g_per_day",
)
# Clinical direction of effect, used as monotone constraints when training tree ensembles: a lower z-score or MUAC
# never lowers the estimated risk, and more danger signs or complications never lower it.
MONOTONE = {"wfa_z": -1, "lhfa_z": -1, "wflh_z": -1, "muac_cm": -1,
            "oedema_present": 1, "appetite_failed": 1, "danger_sign_count": 1, "complication_count": 1}
FORBIDDEN_PARTS = ("true_", "injected", "review", "split", "record_type", "child_id", "district", "period",
                   "outcome", "is_sam", "is_mam", "is_unable", "cmam", "tier", "class")
PREV_MIN_INTERVAL_DAYS, PREV_MAX_INTERVAL_DAYS = 14, 120
RATE_CLIP = 50.0

# Codes for "not scored". Stable: integrators may translate them.
NOT_SCORED = {
    "age_outside_model_range": "The child's age is outside the range the risk model was built for.",
    "muac_missing": "MUAC was not recorded, so the risk model cannot be used.",
    "measurement_not_assessable": "The measurements could not be turned into reliable z-scores.",
    "possible_recording_error": "A recording error is suspected: recheck the measurements first.",
    "data_quality_check_unavailable": "The recording-error check did not run, so the risk model was not used.",
    "invalid_input": "The measurements were not accepted.",
    "model_error": "The risk model could not run. Screening is not affected.",
}


class PriorVisit(Protocol):
    """An earlier visit: anything with these two attributes (the API's PreviousVisit qualifies). Duck-typed so this
    package does not import the growth module."""
    age_days: int
    weight_kg: float


@dataclass(frozen=True)
class Prior:
    age_days: int
    weight_kg: float


def _weight_rate(age_days: int, weight_kg: float, previous: "PriorVisit | None") -> tuple[float, float]:
    """(has_previous, g per day). An unusable earlier visit counts as no earlier visit, never as zero gain."""
    if previous is None:
        return 0.0, 0.0
    interval = age_days - previous.age_days
    if not (PREV_MIN_INTERVAL_DAYS <= interval <= PREV_MAX_INTERVAL_DAYS) or previous.weight_kg <= 0:
        return 0.0, 0.0
    rate = (weight_kg - previous.weight_kg) * 1000.0 / interval
    return 1.0, max(-RATE_CLIP, min(RATE_CLIP, rate))


def risk_features(sex: str, age_days: int, weight_kg: float, length_height_cm: float, measure_position: str,
                  clinical: ClinicalInputs, previous: "PriorVisit | None" = None,
                  age_months_range: tuple[float, float] = (6.0, 60.0)) -> tuple[dict | None, str | None]:
    """Return (features, None), or (None, reason_code) when the child cannot be scored. Never raises for bad input."""
    try:
        base, anthro, _ = features_from_inputs(sex, age_days, weight_kg, length_height_cm, measure_position, clinical)
    except InputError:
        return None, "invalid_input"
    months = base["age_months"]
    if not (age_months_range[0] <= months < age_months_range[1]):
        return None, "age_outside_model_range"
    if clinical.muac_cm is None:
        return None, "muac_missing"
    if base["wfa_missing"] or base["lhfa_missing"] or base["wflh_missing"] or base["implaus_count"]:
        return None, "measurement_not_assessable"
    has_prev, rate = _weight_rate(age_days, weight_kg, previous)
    f = {
        "age_months": months, "sex_male": base["sex_male"],
        "wfa_z": base["wfa_z"], "lhfa_z": base["lhfa_z"], "wflh_z": base["wflh_z"], "muac_cm": float(clinical.muac_cm),
        "oedema_present": float(clinical.oedema is not OedemaGrade.NONE),
        "appetite_failed": float(clinical.appetite.value == "failed"),
        "appetite_not_done": float(clinical.appetite.value == "not_done"),
        "danger_sign_count": float(len(clinical.danger_signs or ())),
        "danger_unknown": float(clinical.danger_signs is None),
        "complication_count": float(len(clinical.complications or ())),
        "compl_unknown": float(clinical.complications is None),
        "has_previous": has_prev, "weight_rate_g_per_day": rate,
    }
    return f, None


def risk_vector(f: dict) -> list[float]:
    return [float(f[n]) for n in RISK_FEATURES]


def feature_phrase(name: str, f: dict) -> str | None:
    """Plain-language statement of a feature value, for the worker. None when the feature is not worth showing."""
    v = f[name]
    return {
        "wfa_z": f"Weight for age is low (z-score {v:.1f})",
        "lhfa_z": f"Length or height for age is low (z-score {v:.1f})",
        "wflh_z": f"Weight for length or height is low (z-score {v:.1f})",
        "muac_cm": f"MUAC is {v:.1f} cm",
        "oedema_present": "Swelling of both feet (oedema) is present",
        "appetite_failed": "The appetite test was failed",
        "appetite_not_done": "The appetite test was not done",
        "danger_sign_count": f"{int(v)} danger sign(s) recorded",
        "danger_unknown": "Danger signs were not assessed",
        "complication_count": f"{int(v)} medical complication(s) recorded",
        "compl_unknown": "Medical complications were not assessed",
        "weight_rate_g_per_day": (f"Weight change since the last visit is {v:.1f} g per day"
                                  if f["has_previous"] else None),
        "age_months": f"Age is {v:.0f} months",
    }.get(name)
