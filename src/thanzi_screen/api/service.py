"""Framework-free core of the API (Phase 6). `screen(payload, view, models) -> dict`.

Calls Phases 1-5, never changes them. A missing or failed ML flag never alters the rules result (D9).
Worker responses carry no HIV information and no raw `referral_text` (D71, D76, D82, D86).
Stateless: nothing is stored or logged from a request. Errors never echo submitted values.
"""
from __future__ import annotations

import math
import re
from enum import Enum

from .. import __version__
from ..anthro import InputError
from ..explain import Explanation, explain_parts, explain_rules_only
from ..explain import messages as M
from ..explain.compose import IGNORED_IN_WHY
from ..ml.features import features_from_inputs
from ..ml.flags import Models, flag_record
from ..preterm import integration as preterm_integration
from ..preterm.routing import PATH_CORRECTED, PATH_PRETERM, route as route_birth
from ..rules import (
    Appetite, ClinicalInputs, Complication, DangerSign, OedemaGrade, RULE_SET_VERSION,
)
from ..rules.models import ClassificationResult
from . import wording
from .security import contains_hiv, scrub_worker

VIEWS = ("worker", "audit")
REQUIRED = ("sex", "age_days", "weight_kg", "length_height_cm", "measure_position", "oedema")
OPTIONAL = ("muac_cm", "appetite", "danger_signs", "complications", "clinically_well_and_alert", "hiv_positive",
            "visible_severe_wasting", "too_weak_to_suckle", "failure_to_gain_weight")
BIRTH_OPTIONAL = ("gestational_age_weeks", "birth_weight_g", "hc_cm", "birth_length_cm", "birth_hc_cm", "sick",
                  "apnoea_last_7_days", "temperature_unstable", "consecutive_days_gaining_weight",
                  "gastric_aspirate_pct", "neonatal_danger_signs")
_BIRTH_NUMBERS = ("gestational_age_weeks", "birth_weight_g", "hc_cm", "birth_length_cm", "birth_hc_cm",
                  "gastric_aspirate_pct")
_BIRTH_BOOLS = ("sick", "apnoea_last_7_days", "temperature_unstable")
_NEONATAL = frozenset(preterm_integration.NEONATAL_SIGNS)
ALLOWED = REQUIRED + OPTIONAL + BIRTH_OPTIONAL
_BOOLS = ("clinically_well_and_alert", "hiv_positive", "visible_severe_wasting", "too_weak_to_suckle",
          "failure_to_gain_weight")
_SAFE_ENGINE_MESSAGE = re.compile(r"^[A-Za-z_]+(?: [A-Za-z_,]+)*$")   # letters only: cannot carry a value


class _Sex(str, Enum):
    MALE = "male"
    FEMALE = "female"


class _Position(str, Enum):
    LENGTH = "length"
    HEIGHT = "height"


class ApiError(Exception):
    """An error with a stable code. The message never contains submitted values."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _bad(field: str, what: str) -> ApiError:
    return ApiError(422, "invalid_request", f"Field '{field}' {what}.")


def _number(payload: dict, field: str) -> float:
    v = payload[field]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _bad(field, "must be a number")
    return float(v)


def _enum(payload: dict, field: str, enum, default=None):
    if field not in payload:
        if default is None:
            raise ApiError(422, "missing_field", f"Missing required field: {field}.")
        return default
    v = payload[field]
    try:
        if not isinstance(v, str):
            raise ValueError
        return enum(v)
    except ValueError:
        raise _bad(field, "must be one of: " + ", ".join(e.value for e in enum)) from None


def _optional_bool(payload: dict, field: str) -> bool | None:
    v = payload.get(field)
    if v is not None and not isinstance(v, bool):
        raise _bad(field, "must be true, false or null")
    return v


def _optional_set(payload: dict, field: str, enum):
    """null or absent means not assessed. A list (even empty) means assessed."""
    v = payload.get(field)
    if v is None:
        return None
    if not isinstance(v, list) or len(v) > 30 or not all(isinstance(x, str) for x in v):
        raise _bad(field, "must be a list of accepted values, or null")
    try:
        return frozenset(enum(x) for x in v)
    except ValueError:
        raise _bad(field, "contains a value that is not accepted") from None


def parse_payload(payload: dict) -> tuple:
    """Validate structure and convert to engine inputs. Ranges and plausibility stay with the engine."""
    if not isinstance(payload, dict):
        raise ApiError(422, "invalid_request", "Request body must be a JSON object.")
    if any(k not in ALLOWED for k in payload):
        raise ApiError(422, "unknown_field", "The request contains a field that is not accepted. "
                                             "Names, identifiers and dates of birth are never accepted.")
    for f in REQUIRED:
        if f not in payload:
            raise ApiError(422, "missing_field", f"Missing required field: {f}.")
    sex = _enum(payload, "sex", _Sex).value
    position = _enum(payload, "measure_position", _Position).value
    age = payload["age_days"]
    if isinstance(age, bool) or not isinstance(age, int):
        raise _bad("age_days", "must be a whole number")
    muac = payload.get("muac_cm")
    if muac is not None:
        muac = _number(payload, "muac_cm")
    clinical = ClinicalInputs(
        oedema=_enum(payload, "oedema", OedemaGrade),
        muac_cm=muac,
        appetite=_enum(payload, "appetite", Appetite, default=Appetite.NOT_DONE),
        danger_signs=_optional_set(payload, "danger_signs", DangerSign),
        complications=_optional_set(payload, "complications", Complication),
        **{f: _optional_bool(payload, f) for f in _BOOLS},
    )
    return (sex, age, _number(payload, "weight_kg"), _number(payload, "length_height_cm"), position, clinical)


def parse_birth(payload: dict) -> tuple[float | None, float | None, dict]:
    """Birth context and preterm-only fields. Structure only; ranges are checked by the routing and the engine."""
    for f in _BIRTH_NUMBERS:
        if payload.get(f) is not None:
            _number(payload, f)
    for f in _BIRTH_BOOLS:
        _optional_bool(payload, f)
    days = payload.get("consecutive_days_gaining_weight")
    if days is not None and (isinstance(days, bool) or not isinstance(days, int)):
        raise _bad("consecutive_days_gaining_weight", "must be a whole number")
    neo = payload.get("neonatal_danger_signs")
    if neo is not None and (not isinstance(neo, list) or len(neo) > 30 or not all(isinstance(x, str) and x in _NEONATAL for x in neo)):
        raise _bad("neonatal_danger_signs", "must be a list of accepted values, or null")
    ga, bw = payload.get("gestational_age_weeks"), payload.get("birth_weight_g")
    extra = {f: payload[f] for f in BIRTH_OPTIONAL[2:] if payload.get(f) is not None}
    if neo is not None:
        extra["neonatal_danger_signs"] = list(neo)
    return (None if ga is None else float(ga)), (None if bw is None else float(bw)), extra


def _engine_message(exc: InputError) -> str:
    text = str(exc)
    return text if _SAFE_ENGINE_MESSAGE.match(text) else "The measurements or clinical inputs were not accepted."


# ---- view building ----
def _reasons(expl: Explanation) -> list[dict]:
    return [{"code": c, "message": t} for c, t in expl.classification_trace.reasons]


def _review(expl: Explanation) -> dict:
    rt = expl.review_trace
    return {"needed": rt.needed, "reasons": [{"code": r.code, "message": r.message} for r in rt.reasons]}


def _ml_flags(flags, expl: Explanation, audit: bool) -> dict:
    review = _review(expl)
    if flags is None:
        return {"available": False, "recording_error": None, "review": review}
    err = flags.recording_error
    rec = {"flagged": err.flagged, "suggested_field": err.suggested_field, "messages": list(err.messages)}
    if audit:
        rec["probability"] = round(err.probability, 6)
    return {"available": True, "recording_error": rec, "review": review, "advisory": flags.advisory}


def _worker_summary(result: ClassificationResult, expl: Explanation) -> list[str]:
    """The Explanation summary, with the programme named for no MAM child (I20, D86)."""
    lines = list(expl.worker_summary)
    if result.classification.value != "MAM":
        return lines
    if "INF.WFA_CLINICIAN" in result.rules_fired:
        head = lines[0]
    else:
        why = [r.worker_text for r in expl.classification_trace.rules
               if r.id not in IGNORED_IN_WHY and r.id not in wording.RULE_CODE_ALIAS][:3]
        head = M.CLASS_PHRASE["MAM"] + (f" Why: {'; '.join(why)}." if why else "")
    return [head, wording.MAM_ACTION, *lines[2:]]


def _display_rules(result: ClassificationResult) -> list[str]:
    return list(dict.fromkeys(wording.RULE_CODE_ALIAS.get(r, r) for r in result.rules_fired))


def _worker_warnings(result: ClassificationResult) -> list[str]:
    kept = [w for w in result.warnings if not contains_hiv(w)]
    if result.classification.value == "MAM":
        kept.append(wording.MAM_WARNING)      # always present for MAM, so its presence says nothing
    return kept


def _common(result: ClassificationResult, expl: Explanation, flags, audit: bool) -> dict:
    mam = result.classification.value == "MAM"
    return {
        "worker_summary": _worker_summary(result, expl),
        "classification": result.classification.value,
        "tier": result.tier.value,
        "reasons": _reasons(expl),
        "ml_flags": _ml_flags(flags, expl, audit),
        "rule_set_version": result.rule_set_version,
        "model_version": expl.model_version,
        "status": wording.STATUS,
        "disclaimer": result.disclaimer,
        "_mam": mam,
    }


def build_worker_view(result: ClassificationResult, expl: Explanation, flags) -> dict:
    out = _common(result, expl, flags, audit=False)
    mam = out.pop("_mam")
    out = {"view": "worker", **out,
           "programme": None if mam else result.programme,
           "rules_fired": _display_rules(result),
           "warnings": _worker_warnings(result)}
    return out


def build_audit_view(result: ClassificationResult, expl: Explanation, flags) -> dict:
    out = _common(result, expl, flags, audit=True)
    out.pop("_mam")
    return {"view": "audit", **out,
            "programme": result.programme,
            "rules_fired": list(result.rules_fired),
            "warnings": list(result.warnings),
            "referral_text": result.referral_text,
            "explanation": expl.to_dict()}


def _under5(args: tuple, view: str, models: Models | None, extra_warnings: list[str] = (), context: dict | None = None) -> dict:
    """The existing under-5 flow. `context` (birth context) is added only when a route other than plain under5 ran."""
    clinical = args[-1]
    features, anthro, result = features_from_inputs(*args)
    if models is None:
        flags, expl = None, explain_rules_only(*args)
    else:
        flags = flag_record(*args, models)
        expl = explain_parts(anthro, result, clinical, flags, features, models)
    out = build_audit_view(result, expl, flags) if view == "audit" else build_worker_view(result, expl, flags)
    if context is not None:
        out = {**out, "route": context["route"], "birth_context": context}
    if extra_warnings:
        out["warnings"] = [*out["warnings"], *extra_warnings]
    return out if view == "audit" else scrub_worker(out)


def screen(payload: dict, view: str = "worker", models: Models | None = None) -> dict:
    """Screen one child. `models=None` is degraded mode: rules result, summary and review check, no ML flag.

    Routing (docs/modules/preterm.md): with gestational_age_weeks and/or birth_weight_g, a baby born under 37 weeks
    or under 2500 g goes to the preterm engine until 50 weeks post-menstrual age, then to the under-5 engine on
    corrected age. Without birth context the request is screened exactly as before.
    """
    if view not in VIEWS:
        raise ApiError(422, "invalid_request", "Field 'view' must be one of: worker, audit.")
    args = parse_payload(payload)
    ga, bw, extra = parse_birth(payload)
    try:
        rt = route_birth(args[1], ga, bw)
        if rt.path == PATH_PRETERM:
            sex, _age, weight, length, position, clinical = args
            pi, warns = preterm_integration.to_preterm_input(
                rt, sex, weight, length, position, extra, clinical.danger_signs, clinical.complications,
                clinical.oedema.value, clinical.too_weak_to_suckle, clinical.failure_to_gain_weight)
            out = preterm_integration.build_preterm_response(
                rt, preterm_integration.run(pi, clinical.oedema.value), warns, view, pi)
            out["status"] = wording.STATUS
            return out if view == "audit" else scrub_worker(out)
        if rt.path == PATH_CORRECTED:
            msg = (f"Age corrected for prematurity: born at {rt.ga_weeks:g} weeks, {rt.age_days} days old, screened as "
                   f"{rt.corrected_age_days} days. CMAM thresholds are applied to the corrected age. The ML recording-error "
                   "flag is not run for corrected ages.")
            return _under5((args[0], rt.age_days_used, *args[2:]), view, None, [msg], preterm_integration.birth_context(rt))
        warns = [w for w in ("Birth weight is under 2500 g but gestational age was not given: preterm screening and "
                             "corrected age were not applied.",) if rt.notes and "gestational_age_missing_for_low_birth_weight" in rt.notes]
        if extra:
            warns.append("Preterm-only fields were given but this baby is not screened by the preterm engine: they were ignored.")
        return _under5(args, view, models, warns)
    except InputError as exc:
        raise ApiError(422, "invalid_input", _engine_message(exc)) from None


def version_info(models: Models | None) -> dict:
    return {"api_version": wording.API_VERSION, "engine_version": __version__, "rule_set_version": RULE_SET_VERSION,
            "model_version": "none" if models is None else models.version, "status": wording.STATUS,
            "disclaimer": "Decision support only. Not a diagnosis. A trained clinician makes the final decision."}
