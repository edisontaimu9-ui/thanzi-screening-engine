"""Framework-free core of the API (Phase 6). `screen(payload, view, models) -> dict`.

Calls Phases 1-5, never changes them. A missing or failed ML flag never alters the rules result (D9).
Worker responses carry no HIV information and no raw `referral_text` (D71, D76, D82, D86).
Stateless: nothing is stored or logged from a request. Errors never echo submitted values.
"""
from __future__ import annotations

import logging
import math
import re
from enum import Enum

from .. import __version__
from ..anthro import InputError
from ..explain import Explanation, explain_parts, explain_rules_only
from ..explain import messages as M
from ..explain.compose import IGNORED_IN_WHY
from ..growth import REVIEW_NOTE, PreviousVisit, assess_trends, assess_weight_velocity
from ..ml.dl import DeepModels
from ..ml.dl.predict import flag_from_features
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

log = logging.getLogger("thanzi.api")
VIEWS = ("worker", "audit")
REQUIRED = ("sex", "age_days", "weight_kg", "length_height_cm", "measure_position", "oedema")
OPTIONAL = ("muac_cm", "appetite", "danger_signs", "complications", "clinically_well_and_alert", "hiv_positive",
            "visible_severe_wasting", "too_weak_to_suckle", "failure_to_gain_weight")
BIRTH_OPTIONAL = ("gestational_age_weeks", "birth_weight_g", "hc_cm", "birth_length_cm", "birth_hc_cm", "sick",
                  "apnoea_last_7_days", "temperature_unstable", "consecutive_days_gaining_weight",
                  "gastric_aspirate_pct", "neonatal_danger_signs", "hypoglycaemia_not_correcting")
_BIRTH_NUMBERS = ("gestational_age_weeks", "birth_weight_g", "hc_cm", "birth_length_cm", "birth_hc_cm",
                  "gastric_aspirate_pct")
_BIRTH_BOOLS = ("sick", "apnoea_last_7_days", "temperature_unstable", "hypoglycaemia_not_correcting")
_NEONATAL = frozenset(preterm_integration.NEONATAL_SIGNS)
GROWTH_OPTIONAL = ("previous_measurement",)
ALLOWED = REQUIRED + OPTIONAL + BIRTH_OPTIONAL + GROWTH_OPTIONAL
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


def parse_payload(payload: dict, require_length: bool = True) -> tuple:
    """Validate structure and convert to engine inputs. Ranges and plausibility stay with the engine.

    `require_length=False` (preterm route only) makes length_height_cm and measure_position optional; if a length is
    given its position is still required. Oedema is always required."""
    if not isinstance(payload, dict):
        raise ApiError(422, "invalid_request", "Request body must be a JSON object.")
    if any(k not in ALLOWED for k in payload):
        raise ApiError(422, "unknown_field", "The request contains a field that is not accepted. "
                                             "Names, identifiers and dates of birth are never accepted.")
    lenient = not require_length and payload.get("length_height_cm") is None
    for f in REQUIRED:
        if lenient and f in ("length_height_cm", "measure_position"):
            continue
        if f not in payload:
            raise ApiError(422, "missing_field", f"Missing required field: {f}.")
    sex = _enum(payload, "sex", _Sex).value
    position = None if lenient and payload.get("measure_position") is None else _enum(payload, "measure_position", _Position).value
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
    length = None if lenient else _number(payload, "length_height_cm")
    return (sex, age, _number(payload, "weight_kg"), length, position, clinical)


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


_PREVIOUS_KEYS = ("age_days", "weight_kg", "length_height_cm", "measure_position", "hc_cm")


def parse_previous(payload: dict) -> PreviousVisit | None:
    """Optional earlier visit. Structure only; the interval and plausibility rules are the growth module's."""
    prev = payload.get("previous_measurement")
    if prev is None:
        return None
    if not isinstance(prev, dict):
        raise _bad("previous_measurement", "must be an object with age_days and weight_kg, or null")
    if any(k not in _PREVIOUS_KEYS for k in prev):
        raise ApiError(422, "unknown_field", "The request contains a field that is not accepted. "
                                             "Names, identifiers and dates of birth are never accepted.")
    for f in ("age_days", "weight_kg"):
        if f not in prev:
            raise ApiError(422, "missing_field", f"Missing required field: previous_measurement.{f}.")
    age = prev["age_days"]
    if isinstance(age, bool) or not isinstance(age, int):
        raise _bad("previous_measurement.age_days", "must be a whole number")
    weight = _number(prev, "weight_kg")
    length = None if prev.get("length_height_cm") is None else _number(prev, "length_height_cm")
    hc = None if prev.get("hc_cm") is None else _number(prev, "hc_cm")
    position = prev.get("measure_position")
    if length is not None and position is None:
        raise ApiError(422, "missing_field", "Missing required field: previous_measurement.measure_position.")
    if position is not None and position not in ("length", "height"):
        raise _bad("previous_measurement.measure_position", "must be one of: length, height")
    return PreviousVisit(age, weight, length, position, hc)


_GROWTH_SKIPPED = ("Growth monitoring was not run: it needs the under-5 route, and this baby is screened on the preterm or "
                   "corrected-age route.")


def _trend_dict(t) -> dict:
    return {"indicator": t.indicator, "assessed": t.assessed, "reason": t.reason, "z_previous": t.z_previous,
            "z_current": t.z_current, "z_change": t.z_change, "direction": t.direction,
            "lines_crossed": list(t.lines_crossed), "status_change": t.status_change, "flagged": t.flagged,
            "messages": list(t.messages), "reference": t.reference, "guide": t.guide}


def _growth(args: tuple, previous: PreviousVisit | None, hc_cm: float | None = None) -> dict | None:
    """Weight-gain velocity and z-score trends for the under-5 route. Advisory. Bad input is a 422, never a 500."""
    if previous is None:
        return None
    sex, age, weight, length, position, clinical = args[0], args[1], args[2], args[3], args[4], args[-1]
    try:
        g = assess_weight_velocity(sex, previous.age_days, previous.weight_kg, age, weight)
        t = assess_trends(sex, previous, age, weight, length, position, hc_cm, clinical.oedema is not OedemaGrade.NONE)
    except ValueError:
        raise ApiError(422, "invalid_input", "previous_measurement must be earlier than this visit and its measurements "
                                             "must be positive numbers.") from None
    review = g.flagged or t.flagged
    return {"assessed": g.assessed, "reason": g.reason, "status": g.status, "flagged": g.flagged,
            "weight_loss": g.weight_loss, "interval_days": g.interval_days, "weight_change_g": g.weight_change_g,
            "rate_g_per_day": g.rate_g_per_day, "reference_low": g.reference_low, "reference_high": g.reference_high,
            "messages": list(g.messages), "reference": g.reference, "advisory": g.advisory,
            "reference_derived": g.reference_derived,
            "trends": {x.indicator: _trend_dict(x) for x in t.indicators},
            "review_suggested": review, "review_note": REVIEW_NOTE if review else None}


def _engine_message(exc: InputError) -> str:
    text = str(exc)
    return text if _SAFE_ENGINE_MESSAGE.match(text) else "The measurements or clinical inputs were not accepted."


# ---- view building ----
def _reasons(expl: Explanation) -> list[dict]:
    return [{"code": c, "message": t} for c, t in expl.classification_trace.reasons]


def _review(expl: Explanation) -> dict:
    rt = expl.review_trace
    return {"needed": rt.needed, "reasons": [{"code": r.code, "message": r.message} for r in rt.reasons]}


def _recording_error(err, audit: bool) -> dict:
    rec = {"flagged": err.flagged, "suggested_field": err.suggested_field, "messages": list(err.messages)}
    if audit:
        rec["probability"] = round(err.probability, 6)
    return rec


def _ml_flags(flags, expl: Explanation, audit: bool, deep_flag=None) -> dict:
    review = _review(expl)
    if flags is None:
        return {"available": False, "recording_error": None, "review": review}
    out = {"available": True, "recording_error": _recording_error(flags.recording_error, audit), "review": review,
           "advisory": flags.advisory}
    if deep_flag is not None:        # second advisory flag (D153): present only when the deep models ran
        out["deep_recording_error"] = _recording_error(deep_flag, audit)
    return out


def _deep_flag(features: dict, deep: DeepModels | None):
    """Deep flag, or None. Never raises: a failure here must not touch the screening result (D9, D154)."""
    if deep is None:
        return None
    try:
        return flag_from_features(features, deep)
    except Exception as exc:         # type only: never the message or the input
        log.warning("Deep flag failed (%s). Screening continues without it.", type(exc).__name__)
        return None


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


def _common(result: ClassificationResult, expl: Explanation, flags, audit: bool, deep_flag=None) -> dict:
    mam = result.classification.value == "MAM"
    return {
        "worker_summary": _worker_summary(result, expl),
        "classification": result.classification.value,
        "tier": result.tier.value,
        "reasons": _reasons(expl),
        "ml_flags": _ml_flags(flags, expl, audit, deep_flag),
        "rule_set_version": result.rule_set_version,
        "model_version": expl.model_version,
        "status": wording.STATUS,
        "disclaimer": result.disclaimer,
        "_mam": mam,
    }


def build_worker_view(result: ClassificationResult, expl: Explanation, flags, deep_flag=None) -> dict:
    out = _common(result, expl, flags, audit=False, deep_flag=deep_flag)
    mam = out.pop("_mam")
    out = {"view": "worker", **out,
           "programme": None if mam else result.programme,
           "rules_fired": _display_rules(result),
           "warnings": _worker_warnings(result)}
    return out


def build_audit_view(result: ClassificationResult, expl: Explanation, flags, deep_flag=None) -> dict:
    out = _common(result, expl, flags, audit=True, deep_flag=deep_flag)
    out.pop("_mam")
    return {"view": "audit", **out,
            "programme": result.programme,
            "rules_fired": list(result.rules_fired),
            "warnings": list(result.warnings),
            "referral_text": result.referral_text,
            "explanation": expl.to_dict()}


def _under5(args: tuple, view: str, models: Models | None, extra_warnings: list[str] = (), context: dict | None = None,
            assessment: dict | None = None, deep: DeepModels | None = None, growth: dict | None = None) -> dict:
    """The existing under-5 flow. `context` (birth context) is added only when a route other than plain under5 ran."""
    clinical = args[-1]
    features, anthro, result = features_from_inputs(*args)
    deep_flag = None
    if models is None:
        flags, expl = None, explain_rules_only(*args)
    else:
        flags = flag_record(*args, models)
        expl = explain_parts(anthro, result, clinical, flags, features, models)
        deep_flag = _deep_flag(features, deep)
    out = (build_audit_view(result, expl, flags, deep_flag) if view == "audit"
           else build_worker_view(result, expl, flags, deep_flag))
    if context is not None:
        out = {**out, "route": context["route"], "birth_context": context}
    if assessment is not None:
        out = {**out, "clinical_assessment": assessment}
    if growth is not None:
        out = {**out, "growth_monitoring": growth}
    if extra_warnings:
        out["warnings"] = [*out["warnings"], *extra_warnings]
    return out if view == "audit" else scrub_worker(display_wording(out))


_DISPLAY_WORDING = (("Failure to gain weight", "Faltering growth (not gaining weight)"),
                    ("failure to gain weight", "faltering growth (not gaining weight)"))


def display_wording(value):
    """Display-only wording for the worker view: 'failure to gain weight' reads as 'faltering growth'. Codes, rule ids and
    the audit view keep the original CMAM terminology, so the audit trace still matches the clinical rule."""
    if isinstance(value, str):
        for old, new in _DISPLAY_WORDING:
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [display_wording(v) for v in value]
    if isinstance(value, dict):
        return {k: (v if k == "code" else display_wording(v)) for k, v in value.items()}
    return value


def _preterm_hint(payload) -> bool:
    """True when the request will be routed to the preterm engine, so length may be optional."""
    try:
        age = payload.get("age_days")
        if isinstance(age, bool) or not isinstance(age, int):
            return False
        ga, bw, _ = parse_birth(payload)
        return route_birth(age, ga, bw).path == PATH_PRETERM
    except (ApiError, InputError, AttributeError):
        return False


def screen(payload: dict, view: str = "worker", models: Models | None = None, deep: DeepModels | None = None) -> dict:
    """Screen one child. `models=None` is degraded mode: rules result, summary and review check, no ML flag.
    `deep` adds the second advisory flag (D153); without it the response is exactly as before.

    Routing (docs/modules/preterm.md): with gestational_age_weeks and/or birth_weight_g, a baby born under 37 weeks
    or under 2500 g goes to the preterm engine until 50 weeks post-menstrual age, then to the under-5 engine on
    corrected age. Without birth context the request is screened exactly as before.
    """
    if view not in VIEWS:
        raise ApiError(422, "invalid_request", "Field 'view' must be one of: worker, audit.")
    args = parse_payload(payload, require_length=not _preterm_hint(payload))
    ga, bw, extra = parse_birth(payload)
    previous = parse_previous(payload)
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
            if previous is not None:
                out["warnings"] = [*out.get("warnings", []), _GROWTH_SKIPPED]
            return out if view == "audit" else scrub_worker(display_wording(out))
        if rt.path == PATH_CORRECTED:
            msg = (f"Age corrected for prematurity: born at {rt.ga_weeks:g} weeks, {rt.age_days} days old, screened as "
                   f"{rt.corrected_age_days} days. CMAM thresholds are applied to the corrected age. The ML recording-error "
                   "flag is not run for corrected ages.")
            if rt.corrected_age_provisional:
                msg += (f" PROVISIONAL: the corrected-age end point of {rt.corrected_age_until_months} months for this "
                        "gestational age is not confirmed. Verify against the clinical reference.")
            if previous is not None:
                msg += " " + _GROWTH_SKIPPED
            return _under5((args[0], rt.age_days_used, *args[2:]), view, None, [msg], preterm_integration.birth_context(rt))
        warns, assessment, ctx = [], None, None
        if "gestational_age_missing_for_low_birth_weight" in rt.notes:
            warns.append("Birth weight is under 2500 g but gestational age was not given: preterm screening and corrected "
                         "age were not applied. Gestational age is not assumed. Refer for clinical assessment.")
            assessment = {"needed": True, "reasons": [{"code": "gestational_age_unknown_low_birth_weight", "message":
                          "Born under 2500 g with unknown gestational age: a clinician should assess whether the baby is preterm."}]}
            ctx = preterm_integration.birth_context(rt)
        hc_used = previous is not None and previous.hc_cm is not None and extra.get("hc_cm") is not None
        ignored = {k: v for k, v in extra.items() if not (k == "hc_cm" and hc_used)}
        if ignored:
            warns.append("Preterm-only fields were given but this baby is not screened by the preterm engine: they were ignored.")
        return _under5(args, view, models, warns, ctx, assessment, deep, _growth(args, previous, extra.get("hc_cm") if hc_used else None))
    except InputError as exc:
        raise ApiError(422, "invalid_input", _engine_message(exc)) from None


def version_info(models: Models | None, deep: DeepModels | None = None) -> dict:
    out = {"api_version": wording.API_VERSION, "engine_version": __version__, "rule_set_version": RULE_SET_VERSION,
           "model_version": "none" if models is None else models.version, "status": wording.STATUS,
           "disclaimer": "Decision support only. Not a diagnosis. A trained clinician makes the final decision."}
    if deep is not None:
        out["deep_model_version"] = deep.version
    return out
