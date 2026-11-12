"""Advisory prediction for one child. Never raises, never changes a classification, tier, referral or warning.

Escalate-only: the result can add "closer follow-up suggested". It never says a child is low risk, never downgrades a rule, and
carries no message at all when the model finds no extra concern. Safeguards, in order, each ending in a "not scored" reason
rather than a guess:

  1. the child's age must be inside the range the model was built for;
  2. no more inputs may be missing than ever were in the training rows;
  3. a gap that was never seen in training is refused, not filled with a typical value.

The inputs are built by `build_features`, which reads only visits up to and including the index visit and never uses the CMAM
classification, tier or referral. The code logs the type of a failure, never its message or the child's data.
"""
from __future__ import annotations

import logging

from .explain import explain
from .features import build_features
from .model import NOT_SCORED, PredictionModel, UnseenMissingError
from .records import Child

log = logging.getLogger("thanzi.api")
ADVISORY = ("Advisory only. It does not change the classification or the referral. No concern from the model does not mean the "
            "child is well: a trained health worker decides.")
_WORDING = {"elevated": "a higher than usual chance", "high": "one of the highest chances"}


def _horizon_text(model: PredictionModel) -> str:
    lo, hi = model.target["horizon_min_days"], model.target["horizon_max_days"]
    return f"between {round(lo / 30.4375)} and {round(hi / 30.4375)} months from now"


def _base(model: PredictionModel) -> dict:
    return {"available": True, "scored": False, "not_scored_reason": None, "not_scored_message": None, "stratum": None,
            "elevated": None, "message": None, "drivers": [], "target": model.target["name"],
            "horizon_days": [model.target["horizon_min_days"], model.target["horizon_max_days"]],
            "model_version": model.version, "non_clinical": not model.clinical_use, "advisory": ADVISORY}


def _not_scored(model: PredictionModel, reason: str) -> dict:
    out = _base(model)
    out.update(not_scored_reason=reason, not_scored_message=NOT_SCORED[reason])
    return out


def assess_features(model: PredictionModel, features: dict, audit: bool = False) -> dict:
    """Score a feature row built by `build_features` (or an equivalent dict with every feature name present)."""
    try:
        reason = model.check_inputs(features)
        if reason:
            return _not_scored(model, reason)
        try:
            x = model.vectorise(features)
        except UnseenMissingError:
            return _not_scored(model, "gap_never_seen_in_training")
        raw, p = model.probability(x)
        stratum = model.stratum(p)
        out = _base(model)
        out.update(scored=True, stratum=stratum, elevated=stratum is not None)
        drivers, audit_part = explain(model, x, features)
        if stratum:
            out["drivers"] = drivers
            out["message"] = (f"The prediction model estimates {_WORDING[stratum]} of {model.target['plain']} {_horizon_text(model)}. "
                              "Consider closer follow-up and a clinician review.")
        if audit:
            out.update(probability=round(p, 6), raw_probability=round(raw, 6), cutoffs=dict(model.cutoffs), model_kind=model.kind,
                       provenance=model.provenance, explanation=audit_part,
                       n_missing_inputs=sum(1 for v in features.values() if v is None))
        return out
    except Exception as exc:        # type only: never the message or the input
        log.warning("Prediction model failed (%s). Screening continues without it.", type(exc).__name__)
        return _not_scored(model, "model_error")


def assess_child(model: PredictionModel, child: Child, index: int, audit: bool = False) -> dict:
    """Score the child at observation `index`, using that visit and earlier ones only."""
    try:
        features = build_features(child, index)
    except Exception as exc:
        log.warning("Prediction inputs failed (%s). Screening continues without it.", type(exc).__name__)
        return _not_scored(model, "invalid_input")
    return assess_features(model, features, audit)
