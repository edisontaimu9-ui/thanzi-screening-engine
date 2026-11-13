"""Why an input is empty. Three plain states, never mixed, never filled in:

  not_assessed   the question was not asked or not answered (clinical history, feeding, maternal, household);
  not_applicable the input cannot exist for this child (no earlier visit, deworming under 12 months, first birth);
  unavailable    it was given but cannot be used (an earlier visit that is invalid or not comparable).

A model's required inputs are its pathway minimum. Everything else may be empty without stopping the score.
"""
from __future__ import annotations

from .features import FEATURES

NOT_ASSESSED, NOT_APPLICABLE, UNAVAILABLE = "not_assessed", "not_applicable", "unavailable"
HISTORY_NONE, HISTORY_UNAVAILABLE, HISTORY_OK = "none", "unavailable", "ok"
_RANK = {NOT_APPLICABLE: 0, NOT_ASSESSED: 1, UNAVAILABLE: 2}


def feature_state(name: str, features: dict, history: str) -> str:
    spec = FEATURES[name]
    if spec.group == "longitudinal":
        return UNAVAILABLE if history == HISTORY_UNAVAILABLE else NOT_APPLICABLE
    if name == "deworming_last_6mo" and (features.get("age_months") or 99) < 12:
        return NOT_APPLICABLE
    if name.startswith("birth_interval") and features.get("birth_order") == 1:
        return NOT_APPLICABLE
    return NOT_ASSESSED


def input_status(features: dict, history: str = HISTORY_NONE) -> dict:
    """{state: [group, ...]} for every group that has an empty input. Group level, so no value or child detail leaves the service."""
    worst: dict[str, str] = {}
    for name, spec in FEATURES.items():
        if features.get(name) is None:
            s = feature_state(name, features, history)
            if spec.group not in worst or _RANK[s] > _RANK[worst[spec.group]]:
                worst[spec.group] = s
    return {s: sorted(g for g, v in worst.items() if v == s) for s in (NOT_ASSESSED, NOT_APPLICABLE, UNAVAILABLE)}
