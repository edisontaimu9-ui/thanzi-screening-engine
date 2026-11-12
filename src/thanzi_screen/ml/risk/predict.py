"""Advisory risk assessment for one child. Never raises, never changes a classification, tier, referral or warning.

Escalate-only: the result can add "closer follow-up suggested". It never says a child is low risk, never downgrades a
rule, and says nothing at all when the model sees no extra concern (the worker response then carries no message).
"""
from __future__ import annotations

import logging

from ...rules import ClinicalInputs
from .features import NOT_SCORED, PriorVisit, feature_phrase, risk_features, risk_vector
from .model import RiskModel

log = logging.getLogger("thanzi.api")
ADVISORY = ("Advisory only. It does not change the classification or the referral. No concern from the model does not "
            "mean the child is well: a trained health worker decides.")
MAX_DRIVERS = 3


def _unavailable(model: RiskModel, reason: str) -> dict:
    return {"available": True, "scored": False, "not_scored_reason": reason, "not_scored_message": NOT_SCORED[reason],
            "elevated": None, "message": None, "drivers": [], "target": model.target["name"],
            "horizon_weeks": model.target["horizon_weeks"], "model_version": model.version,
            "non_clinical": not model.clinical_use, "advisory": ADVISORY}


def _drivers(model: RiskModel, x: list[float], f: dict) -> tuple[list[dict], dict]:
    base, phi, unit = model.contributions(x)
    order = sorted(range(len(phi)), key=lambda i: (-phi[i], i))
    shown = []
    for i in order:
        name = model.model.names[i]
        text = feature_phrase(name, f) if phi[i] > 0 else None
        if text:
            shown.append({"feature": name, "text": text, "direction": "raises"})
        if len(shown) == MAX_DRIVERS:
            break
    audit = {"unit": unit, "baseline": round(base, 6),
             "contributions": [{"feature": n, "value": round(v, 6), "contribution": round(c, 6)}
                               for n, v, c in sorted(zip(model.model.names, x, phi), key=lambda t: (-abs(t[2]), t[0]))]}
    return shown, audit


def assess_risk(model: RiskModel, sex: str, age_days: int, weight_kg: float, length_height_cm: float,
                measure_position: str, clinical: ClinicalInputs, previous: PriorVisit | None,
                recording_error_flagged: bool | None, audit: bool = False) -> dict:
    """`recording_error_flagged` is None when the recording-error check did not run."""
    try:
        if recording_error_flagged is None:
            return _unavailable(model, "data_quality_check_unavailable")
        if recording_error_flagged:
            return _unavailable(model, "possible_recording_error")
        f, reason = risk_features(sex, age_days, weight_kg, length_height_cm, measure_position, clinical, previous,
                                  model.age_months_range)
        if f is None:
            return _unavailable(model, reason)
        x = risk_vector(f)
        elevated, raw, p = model.elevated(x)
        out = _unavailable(model, "model_error")
        out.update(scored=True, not_scored_reason=None, not_scored_message=None, elevated=elevated)
        drivers_audit = None
        if elevated:
            out["drivers"], drivers_audit = _drivers(model, x, f)
            out["message"] = (f"The risk model estimates a higher than usual chance of {model.target['plain']} within "
                              f"{model.target['horizon_weeks']} weeks. Consider closer follow-up and a clinician review.")
        if audit:
            out.update(probability=round(p, 6), raw_probability=round(raw, 6), threshold=model.threshold,
                       model_kind=model.kind, provenance=model.provenance)
            if drivers_audit is None:
                _, drivers_audit = _drivers(model, x, f)
            out["explanation"] = drivers_audit
        return out
    except Exception as exc:        # type only: never the message or the input
        log.warning("Risk model failed (%s). Screening continues without it.", type(exc).__name__)
        return _unavailable(model, "model_error")
