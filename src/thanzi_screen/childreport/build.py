"""Individual child screening report, built from the WORKER view of a screening result (Phase 9). Standard library only.

Contract, all tested:
  * Input is the worker view only. The audit view is refused, so nothing from it (and no HIV information) can reach the report.
  * The screening result is copied, never recomputed: classification, tier, programme, rules fired, reasons and summary lines are
    identical to the input.
  * Everything after the screening result is escalate-only. Growth, recording-error, review, assessment and prediction findings can
    add items and raise the attention level from routine to raised. Nothing lowers a level, and the level never goes below the one
    the screening tier sets.
  * No finding is reassurance: a missing or empty prediction says so in words.
  * Report-owned sentences live in `wording.py` (draft, pending clinical review). Everything else is quoted from the input.
  * It fails closed: an input that is not a worker view, or any output that mentions HIV, raises ValueError.
"""
from __future__ import annotations

import copy
import json

from ..references import CMAM_TITLE, COIN_TITLE, WHO_STANDARDS_TITLE
from . import wording as W

REPORT_VERSION = "child_report_0.1"
LEVELS = ("routine", "raised", "recheck", "urgent")     # `recheck` and `urgent` come from the screening result only
_TIER_LEVEL = {"low_risk": "routine", "mam": "raised", "urgent": "urgent", "recheck": "recheck"}
_PRETERM_LEVEL = {"routine": "routine", "follow_up": "raised", "refer": "raised", "urgent_refer": "urgent"}
_TIER_ACTION = {"urgent": "action.urgent", "mam": "action.mam", "low_risk": "action.low_risk", "recheck": "action.recheck"}


def _has_hiv(obj) -> bool:
    return "hiv" in json.dumps(obj, default=str).lower()


def _messages(items) -> list[str]:
    """Plain text from a list of strings or of {code, message} dicts."""
    out = []
    for i in items or []:
        m = i.get("message") if isinstance(i, dict) else i
        if isinstance(m, str) and m:
            out.append(m)
    return out


def _base_level(s: dict, preterm: bool) -> tuple[str, bool]:
    """(level, known). An unknown tier or level is never read as routine."""
    key = s.get("preterm_level") if preterm else s.get("tier")
    table = _PRETERM_LEVEL if preterm else _TIER_LEVEL
    if key in table:
        return table[key], True
    return "raised", False


def _result(s: dict, preterm: bool) -> dict:
    out = {"route": s.get("route") or "under5", "tier": s.get("tier"), "summary": list(s.get("worker_summary") or []),
           "reasons": _messages(s.get("reasons")), "rule_set_version": s.get("rule_set_version")}
    if preterm:
        out |= {"preterm_level": s.get("preterm_level"), "birth_classification": copy.deepcopy(s.get("birth_classification")),
                "classification": None, "programme": None, "rules_fired": []}
    else:
        out |= {"classification": s.get("classification"), "programme": s.get("programme"),
                "rules_fired": list(s.get("rules_fired") or []), "preterm_level": None, "birth_classification": None}
    return out


def _action(s: dict, preterm: bool, known: bool) -> dict:
    if preterm:
        return {"statement": W.text("action.preterm"), "steps": _messages(s.get("actions")), "note": s.get("note")}
    if not known:
        return {"statement": W.text("action.unplaced"), "steps": [], "note": None}
    return {"statement": W.text(_TIER_ACTION[s["tier"]]), "steps": [], "note": None}


def _check_items(s: dict) -> list[dict]:
    items: list[dict] = []
    flags = s.get("ml_flags") or {}
    rec = flags.get("recording_error") or {}
    if rec.get("flagged"):
        items += [{"source": "recording_error", "text": m} for m in _messages(rec.get("messages"))]
        if rec.get("suggested_field"):
            items.append({"source": "recording_error", "field": rec["suggested_field"],
                          "text": f"Check the entry for: {rec['suggested_field']}."})
    deep = flags.get("deep_recording_error") or {}
    if deep.get("flagged"):
        items += [{"source": "recording_error", "text": m} for m in _messages(deep.get("messages"))]
    review = flags.get("review") or {}
    if review.get("needed"):
        items += [{"source": "review", "text": m} for m in _messages(review.get("reasons"))]
    assess = s.get("clinical_assessment") or {}
    if assess.get("needed"):
        items.append({"source": "clinical_assessment", "text": W.text("assessment.lead")})
        items += [{"source": "clinical_assessment", "text": m} for m in _messages(assess.get("reasons"))]
    items += [{"source": "warning", "text": m} for m in _messages(s.get("warnings"))]
    seen, out = set(), []
    for it in items:                                  # the same sentence once, in the order it was found
        if it["text"] not in seen:
            seen.add(it["text"])
            out.append(it)
    return out


def _growth(s: dict) -> dict | None:
    g = s.get("growth_monitoring")
    if not g:
        return None
    flagged_trends = [t for t in (g.get("trends") or {}).values() if isinstance(t, dict) and t.get("flagged")]
    msgs = _messages(g.get("messages"))
    for t in flagged_trends:
        msgs += _messages(t.get("messages"))
    return {"assessed": bool(g.get("assessed")), "review_suggested": bool(g.get("review_suggested")),
            "lead": W.text("growth.lead"), "messages": list(dict.fromkeys(msgs)), "review_note": g.get("review_note")}


def _prediction(s: dict) -> dict:
    p = s.get("ml_prediction")
    if not p:
        return {"status": "not_run", "elevated": False, "statement": W.text("prediction.not_run"), "message": None,
                "concerns": [], "drivers": [], "not_scored": []}
    not_scored = [{"target": n.get("target"), "reason": n.get("reason"), "message": n.get("message")}
                  for n in (p.get("not_scored") or []) if isinstance(n, dict)]
    if p.get("elevated"):
        status, stmt = "concern", W.text("prediction.concern")
    elif p.get("scored"):
        status, stmt = "no_concern", W.text("prediction.no_concern")
    else:
        status, stmt = "not_scored", W.text("prediction.not_scored")
    if status != "not_scored" and not_scored:
        stmt += " " + W.text("prediction.partly_scored")
    return {"status": status, "elevated": status == "concern", "statement": stmt, "message": p.get("message"),
            "concerns": [{"plain": c.get("plain"), "stratum": c.get("stratum")} for c in p.get("concerns") or [] if isinstance(c, dict)],
            "drivers": [d.get("text") or d.get("plain") or d.get("message") for d in p.get("drivers") or [] if isinstance(d, dict)
                        and (d.get("text") or d.get("plain") or d.get("message"))],
            "not_scored": not_scored}


def _sources(preterm: bool) -> list[str]:
    return [COIN_TITLE, CMAM_TITLE, WHO_STANDARDS_TITLE] if preterm else [CMAM_TITLE, WHO_STANDARDS_TITLE]


def build_child_report(screen: dict) -> dict:
    """One child's report from the worker view of a screening result. Raises ValueError for anything else."""
    if not isinstance(screen, dict) or screen.get("view") != "worker":
        raise ValueError("the child report is built from the worker view of a screening result")
    preterm = screen.get("route") == "preterm"
    if "tier" not in screen or not screen.get("worker_summary") or ("preterm_level" if preterm else "classification") not in screen:
        raise ValueError("not a screening result")
    s = copy.deepcopy(screen)
    level, known = _base_level(s, preterm)
    growth, prediction = _growth(s), _prediction(s)
    if level == "routine" and ((growth or {}).get("review_suggested") or prediction["elevated"]):
        level = "raised"                              # escalate only: a finding can lift routine, nothing can lower a level
    checks = _check_items(s)
    report = {
        "report_version": REPORT_VERSION,
        "wording": {"version": W.WORDING_VERSION, "status": W.REVIEW_STATUS, "notice": W.text("banner.draft")},
        "not_a_diagnosis": W.text("banner.not_diagnosis"),
        "attention": {"level": level, "label": W.text(f"level.{level}"),
                      "raised_by_findings": level != _base_level(s, preterm)[0], "changes_classification": False},
        "result": _result(s, preterm),
        "action": _action(s, preterm, known),
        "check_before_acting": {"lead": W.text("check.lead"), "items": checks} if checks else None,
        "growth": growth,
        "prediction": prediction,
        "limits": [W.text("limits.rules_decide"), W.text("limits.flags_advisory"), W.text("limits.worried"), s.get("status"),
                   s.get("disclaimer")],
        "sources": _sources(preterm),
    }
    report["limits"] = [x for x in report["limits"] if isinstance(x, str) and x]
    if _has_hiv(report):
        raise ValueError("the report would contain HIV information")
    return report
