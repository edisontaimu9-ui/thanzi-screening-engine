"""One screening summary from several one-target prediction results. Standard library only.

Each model predicts one target. The health worker gets one result. Rules this module keeps, all tested:

  * escalate only: it can add a concern, never remove one, and there is no low-risk label. No concern is not reassurance;
  * it never sees the deterministic classification, tier or referral, so it cannot change them. The rules decide;
  * one result per target: where several models cover a target (for example a full and an anthropometric pathway), the first one
    that could be scored is used, in the order the models were given (put the fullest pathway first);
  * what could not be scored is listed with its reason, never dropped, and never filled in.
"""
from __future__ import annotations

from .predict import ADVISORY
from .status import NOT_APPLICABLE, NOT_ASSESSED, UNAVAILABLE

AUTHORITY = ("The deterministic classification and referral rules decide. This summary is decision support: it adds a concern, "
             "it never lowers one, and it is not a diagnosis.")
TARGET_ORDER = ("future_sam", "future_wasting", "future_faltering")        # most severe first
_RANK = {"high": 2, "elevated": 1}
MAX_DRIVERS = 3


def _order(target: str) -> int:
    return TARGET_ORDER.index(target) if target in TARGET_ORDER else len(TARGET_ORDER)


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _horizon(blocks: list[dict]) -> str:
    lo, hi = min(b["horizon_days"][0] for b in blocks), max(b["horizon_days"][1] for b in blocks)
    return f"between {round(lo / 30.4375)} and {round(hi / 30.4375)} months from now"


def one_per_target(blocks: list[dict]) -> list[dict]:
    """The first scored block for each target, else the first block for it. Order of first appearance is kept."""
    chosen: dict[str, dict] = {}
    for b in blocks:
        cur = chosen.get(b["target"])
        if cur is None or (not cur["scored"] and b["scored"]):
            chosen[b["target"]] = b
    return list(chosen.values())


_STATES = (NOT_ASSESSED, NOT_APPLICABLE, UNAVAILABLE)
_STATE_RANK = {NOT_APPLICABLE: 0, NOT_ASSESSED: 1, UNAVAILABLE: 2}


def merge_inputs(blocks: list[dict]) -> dict | None:
    """Empty-input groups across the models used, each group under its most serious state (unavailable, not assessed, not applicable)."""
    worst: dict[str, str] = {}
    for b in blocks:
        for state, groups in (b.get("inputs") or {}).items():
            for g in groups:
                if g not in worst or _STATE_RANK[state] > _STATE_RANK[worst[g]]:
                    worst[g] = state
    if not any(b.get("inputs") for b in blocks):
        return None
    return {s: sorted(g for g, v in worst.items() if v == s) for s in _STATES}


def consolidate(blocks: list[dict], audit: bool = False) -> dict:
    """`blocks` are the results of `assess_child` / `assess_features`, one per loaded model."""
    used = one_per_target(blocks)
    scored = [b for b in used if b["scored"]]
    flagged = sorted((b for b in scored if b["stratum"]), key=lambda b: (-_RANK[b["stratum"]], _order(b["target"])))
    out = {"available": True, "scored": bool(scored), "elevated": None, "stratum": None, "message": None, "drivers": [], "concerns": [],
           "not_scored": [{"target": b["target"], "pathway": b["pathway"], "reason": b["not_scored_reason"],
                           "message": b["not_scored_message"]} for b in used if not b["scored"]],
           "inputs": merge_inputs(used), "targets_scored": [b["target"] for b in scored],
           "non_clinical": any(b["non_clinical"] for b in blocks), "advisory": ADVISORY, "authority": AUTHORITY,
           "model_versions": [b["model_version"] for b in used]}
    if scored:
        out["elevated"] = bool(flagged)
    if flagged:
        out["stratum"] = flagged[0]["stratum"]
        out["concerns"] = [{"target": b["target"], "plain": b["target_plain"], "stratum": b["stratum"],
                            "horizon_days": b["horizon_days"], "pathway": b["pathway"]} for b in flagged]
        clauses = []
        for s, phrase in (("high", "one of the highest chances of"), ("elevated", "a higher than usual chance of")):
            plains = [b["target_plain"] for b in flagged if b["stratum"] == s]
            if plains:
                clauses.append(f"{phrase} {_join(plains)}")
        out["message"] = (f"The prediction models estimate {'; and '.join(clauses)} {_horizon(flagged)}. "
                          "Consider closer follow-up and a clinician review.")
        seen = []
        for b in flagged:
            for d in b["drivers"]:
                if d["feature"] not in [x["feature"] for x in seen] and len(seen) < MAX_DRIVERS:
                    seen.append(d)
        out["drivers"] = seen
    if audit:
        out["models"] = blocks
    return out
