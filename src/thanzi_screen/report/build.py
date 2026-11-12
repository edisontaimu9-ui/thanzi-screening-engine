"""Compose one report from two independent module outputs.

Contract:
- `deterministic_screening` is the screening module's output, copied verbatim.
- `ml_prediction` is the prediction module's output, copied verbatim, or an explicit not_run block.
- `attention` is a short plain-language reading across both. It can only RAISE attention: an elevated prediction on a
  child the rules call low risk asks for closer follow-up. A low prediction is never reassurance, and nothing here changes
  a classification, tier or referral.
"""
from __future__ import annotations

import copy

REPORT_VERSION = "report_0.1"
SCREEN_MODULE = "deterministic_screening"
PREDICT_MODULE = "ml_prediction"
NOT_RUN_REASONS = {"not_requested", "module_unavailable", "not_scored"}

_ADVISORY = ("The screening result follows the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, "
             "Malawi, 2016 and decides referral. The prediction is a separate advisory estimate. It can add a concern. "
             "It never lowers one and never changes the screening result. A trained health worker decides.")


def _not_run(reason: str) -> dict:
    if reason not in NOT_RUN_REASONS:
        raise ValueError("unknown reason")
    return {"module": PREDICT_MODULE, "status": "not_run", "reason": reason, "elevated": False,
            "note": "No prediction was made. This is not reassurance."}


def build_report(screening: dict, prediction: dict | None = None, not_run_reason: str = "not_requested") -> dict:
    if not isinstance(screening, dict) or screening.get("module") != SCREEN_MODULE:
        raise ValueError("screening must be the output of the deterministic screening module")
    if prediction is not None and (not isinstance(prediction, dict) or prediction.get("module") != PREDICT_MODULE):
        raise ValueError("prediction must be the output of the ML prediction module")
    scr = copy.deepcopy(screening)
    pred = copy.deepcopy(prediction) if prediction is not None else _not_run(not_run_reason)
    tier = scr["classification"]["tier"]
    notes: list[str] = []
    if tier == "recheck" or scr.get("status") == "recheck_measurements":
        notes.append("Recheck the measurements before relying on any result.")
    if scr["longitudinal"]["growth_faltering"]:
        notes.append("Growth faltering is flagged from the visit history. A clinician should review feeding, illness and measurements.")
    elevated = bool(pred.get("elevated"))
    if elevated and tier == "low_risk":
        notes.append("The prediction is elevated although the screening result is low risk. Arrange closer follow-up.")
    elif elevated:
        notes.append("The prediction is also elevated. The screening referral stands.")
    level = "recheck" if (tier == "recheck" or scr.get("status") == "recheck_measurements") else (
        "urgent" if tier == "urgent" else "raised" if (tier == "mam" or elevated or scr["longitudinal"]["growth_faltering"]) else "routine")
    return {
        "report_version": REPORT_VERSION,
        "deterministic_screening": scr,
        "ml_prediction": pred,
        "attention": {"level": level, "notes": notes, "derived_from": ["deterministic_screening", "ml_prediction"],
                      "changes_classification": False},
        "independence": {"report_changes_either_module": False},
        "advisory": _ADVISORY,
    }
