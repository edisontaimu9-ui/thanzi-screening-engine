"""Compose one Explanation from the Phase 1-4 outputs (Phase 5). Describes only; never alters a result (D9)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..ml.features import features_from_inputs, vector
from ..ml.flags import MlFlags, Models, flag_record
from ..rules import ClinicalInputs
from ..rules.rules_v2016 import PLACEHOLDER
from . import messages as M
from .ml_explain import FlagTrace, build_flag_trace
from .review_explain import ReviewTrace, build_review_trace
from .trace import ClassificationTrace, build_trace, context

MAX_SUMMARY_LINES = 3
IGNORED_IN_WHY = ("DATA.IMPLAUSIBLE_IGNORED", "LOW.NONE")


@dataclass(frozen=True)
class Explanation:
    summary: tuple[str, ...]                 # worker view, at most 3 lines
    classification_trace: ClassificationTrace
    flag_trace: FlagTrace
    review_trace: ReviewTrace
    limits: tuple[str, ...]
    rule_set_version: str
    model_version: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, **kw) -> str:
        return json.dumps(self.to_dict(), **kw)


def _clean(text: str) -> str:
    return text.replace(PLACEHOLDER, "").strip()


def _line_classification(result, trace: ClassificationTrace, ctx: dict) -> str:
    cls = result.classification.value
    rules = result.rules_fired
    if cls == "MAM" and "INF.WFA_CLINICIAN" in rules:
        return f"{M.INFANT_WFA_PHRASE} Why: {M.RULE_WORKER['INF.WFA_CLINICIAN'].format_map(_Safe(ctx))}."
    head = M.CLASS_PHRASE[cls]
    if cls in ("UNABLE_TO_CLASSIFY", "SAM_ASSESS") and result.reasons:
        need = "; ".join(t for _, t in trace.reasons[:3])
        return f"{head} Needed: {need}." if cls == "UNABLE_TO_CLASSIFY" else \
            f"{head} Still needed to choose OTP or inpatient care: {need}."
    if cls == "low_risk":
        if trace.pathway == "infant":
            return f"{head} Weight-for-length z {ctx['wflh']}."
        muac = "MUAC not entered" if ctx["muac"] == "?" else f"MUAC {ctx['muac']} cm"
        return f"{head} {muac}; weight-for-length/height z {ctx['wflh']}."
    why = [r.worker_text for r in trace.rules if r.id not in IGNORED_IN_WHY][:3]
    return f"{head} Why: {'; '.join(why)}." if why else head


class _Safe(dict):
    def __missing__(self, k):
        return "?"


def _line_action(result) -> str:
    if "MAM.HIV_OTP" in result.rules_fired:
        return M.OTP_ACTION           # no HIV wording for the worker view (Q7)
    return _clean(result.referral_text)


def _line_flags(flags: MlFlags, flag_trace: FlagTrace) -> str | None:
    parts = []
    err = flags.recording_error
    if err.flagged:
        why = "; ".join(c.text for c in flag_trace.top_raising[:2])
        parts.append(f"Recording check: {err.messages[0]} Why: {why}." if why else f"Recording check: {err.messages[0]}")
    if flags.review.needed:
        extra = len(flags.review.messages) - 1
        more = f" (+{extra} more reason{'s' if extra > 1 else ''})" if extra else ""
        parts.append(f"Review: {flags.review.messages[0]}{more}")
    return " ".join(parts) if parts else None


def explain_parts(anthro, result, clinical: ClinicalInputs, flags: MlFlags, features: dict, models: Models) -> Explanation:
    trace = build_trace(anthro, clinical, result)
    ftrace = build_flag_trace(models, vector(features), features, flags)
    rtrace = build_review_trace(anthro, result, clinical, flags.review)
    lines = [_line_classification(result, trace, context(anthro, clinical)), _line_action(result)]
    flag_line = _line_flags(flags, ftrace)
    if flag_line:
        lines.append(flag_line)
    return Explanation(tuple(lines[:MAX_SUMMARY_LINES]), trace, ftrace, rtrace, M.LIMITS,
                       result.rule_set_version, models.version)


def explain(sex: str, age_days: int, weight_kg: float, length_height_cm: float, measure_position: str,
            clinical: ClinicalInputs, models: Models) -> Explanation:
    """Run Phases 1-4 for one record and explain the outputs. Raises InputError on invalid input."""
    features, anthro, result = features_from_inputs(sex, age_days, weight_kg, length_height_cm, measure_position, clinical)
    flags = flag_record(sex, age_days, weight_kg, length_height_cm, measure_position, clinical, models)
    return explain_parts(anthro, result, clinical, flags, features, models)
