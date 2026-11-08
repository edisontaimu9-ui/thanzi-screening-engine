"""Glue between the API request and the preterm engine. The engine's logic is not changed here.

- Maps the under-5 inputs that overlap with the preterm triggers onto `PretermInput` (no duplicate fields).
- Applies the one documented level map (routing_config.json -> `routing.tier_for`).
- Builds the response dicts for the worker and audit views.
"""
from __future__ import annotations

import copy
import math

from ..anthro import InputError
from . import engine as E
from .routing import CONFIG, NO_TIER_NOTE, Route, at_least, tier_for

RULE_SET_VERSION = "preterm_coin2017_fenton2025"
NEONATAL_SIGNS = ("bilious_vomiting", "apnoea", "cyanosis", "abdominal_distension", "blood_in_stool", "feed_intolerance")
LEVEL_PHRASE = {
    "routine": "No referral needed now. Continue routine care and growth monitoring.",
    "follow_up": "Needs close follow-up. Review again as set out below.",
    "refer": "Refer for assessment and nutrition review.",
    "urgent_refer": "Urgent referral. Stabilise, then transfer.",
}
DISCLAIMER = "Decision support only. Not a diagnosis. A trained clinician makes the final decision."


def attribution() -> str:
    m = E.LMS["meta"]
    return f"Growth data: {m['source']}. Licence: {m['license']}."


def _positive(name: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise InputError(f"{name} must be a positive finite number")
    return float(v)


def _opt(name: str, v):
    return None if v is None else _positive(name, v)


def pi_hypo(extra: dict) -> bool:
    return bool(extra.get("hypoglycaemia_not_correcting")) or CONFIG["hypoglycaemia"]["complication_means_not_correcting"]


def to_preterm_input(route: Route, sex: str, weight_kg: float, length_height_cm: float | None, position: str | None,
                     extra: dict, danger_signs, complications, oedema: str, too_weak_to_suckle,
                     failure_to_gain_weight) -> tuple[E.PretermInput, list[str]]:
    """Return the engine input and any warnings. Raises InputError for input the preterm path cannot use."""
    # Length is optional on this route (the engine skips the length z-score without it). If given it must be a length.
    if length_height_cm is not None and position != "length":
        raise InputError("measure_position must be length for a baby screened as preterm")
    wk = CONFIG["plausible_weights"]["weight_kg_on_preterm_route"]
    if not wk["min"] <= _positive("weight_kg", weight_kg) <= wk["max"]:
        raise InputError("weight_kg is outside the supported range, give kilograms")
    ds = {d.value for d in danger_signs} if danger_signs is not None else set()
    cx = {c.value for c in complications} if complications is not None else set()
    neo = set(extra.get("neonatal_danger_signs") or ())
    warnings: list[str] = []
    if danger_signs is None and extra.get("neonatal_danger_signs") is None:
        warnings.append("Danger signs were not assessed. Assess them: only danger signs can make this an urgent referral.")
    gaining = extra.get("consecutive_days_gaining_weight")
    if gaining is not None and (isinstance(gaining, bool) or not isinstance(gaining, int) or gaining < 0):
        raise InputError("consecutive_days_gaining_weight must not be negative")
    asp = extra.get("gastric_aspirate_pct")
    if asp is not None and (isinstance(asp, bool) or not isinstance(asp, (int, float)) or not math.isfinite(asp)
                            or not 0 <= asp <= 100):
        raise InputError("gastric_aspirate_pct is outside the supported range")
    if gaining is None and failure_to_gain_weight:
        gaining = 0
    mapped_complications = {"hypoglycaemia", "severe_dehydration"}
    sick = bool(extra.get("sick")) or bool(ds) or bool(cx)
    if cx - mapped_complications:
        warnings.append("Medical complications were reported. The baby is treated as sick: refer.")
    if "hypoglycaemia" in cx and not pi_hypo(extra):
        warnings.append("Hypoglycaemia reported without saying whether it is correcting: treated as a complication (refer). "
                        "Say hypoglycaemia_not_correcting if it is not responding to treatment.")
    if oedema != "none":
        warnings.append("Oedema reported: weight z-scores are unreliable. Oedema is an inpatient criterion in an infant "
                        "under CMAM 2016 Table 5.")
    pi = E.PretermInput(
        sex=sex, ga_weeks=route.ga_weeks, birth_weight_g=route.birth_weight_g, age_days=route.age_days,
        weight_g=round(_positive("weight_kg", weight_kg) * 1000, 3),
        length_cm=None if length_height_cm is None else _positive("length_height_cm", length_height_cm),
        hc_cm=_opt("hc_cm", extra.get("hc_cm")),
        sick=sick,
        cannot_feed="unable_to_drink_or_breastfeed" in ds or bool(too_weak_to_suckle),
        apnoea_7d=bool(extra.get("apnoea_last_7_days")),
        temp_unstable=bool(extra.get("temperature_unstable")),
        gaining_days=gaining,
        aspirate_pct=asp,
        birth_length_cm=_opt("birth_length_cm", extra.get("birth_length_cm")),
        birth_hc_cm=_opt("birth_hc_cm", extra.get("birth_hc_cm")),
        bilious_vomiting="bilious_vomiting" in neo,
        convulsions="convulsions" in ds,
        apnoea_now="apnoea" in neo,
        cyanosis="cyanosis" in neo,
        hypoglycaemia_uncorrected=bool(extra.get("hypoglycaemia_not_correcting"))
        or ("hypoglycaemia" in cx and CONFIG["hypoglycaemia"]["complication_means_not_correcting"]),
        abdominal_distension="abdominal_distension" in neo,
        blood_in_stool="blood_in_stool" in neo,
        feed_intolerance="feed_intolerance" in neo,
        dehydrated="severe_dehydration" in cx,
        lethargic="lethargy_not_alert" in ds or "unconsciousness" in ds,
    )
    return pi, warnings


def run(pi: E.PretermInput, oedema: str) -> dict:
    """Engine result plus the integration level. Oedema can raise the level to at most the configured minimum."""
    raw = E.screen(pi)
    out = copy.deepcopy(raw)
    ref = out["referral"]
    if oedema != "none":
        minimum = CONFIG["oedema_on_preterm_route"]["min_preterm_level_by_grade"][oedema]
        ref["level"] = at_least(ref["level"], minimum)
        ref["reasons"].append(f"oedema {oedema} reported: possible severe acute malnutrition sign, escalate to at least {minimum}")
        if minimum == "urgent_refer":
            ref["actions"].extend(E.R["urgent_triggers"]["stabilise_before_transfer"])
    return {"raw": raw, "result": out}


def _clean(v):
    """NaN is not valid JSON; use null."""
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def ml_row(pi: E.PretermInput) -> dict:
    return {k: _clean(v) for k, v in E.features(pi).items()}


def birth_context(route: Route) -> dict:
    return {
        "route": route.path, "route_reason": route.reason,
        "gestational_age_weeks": route.ga_weeks, "birth_weight_g": route.birth_weight_g,
        "born_preterm": route.preterm_birth, "low_birth_weight": route.low_birth_weight,
        "age_days": route.age_days, "pma_weeks": route.pma_weeks,
        "corrected_age_days": route.corrected_age_days,
        "corrected_age_until_chronological_months": route.corrected_age_until_months,
        "corrected_age_end_provisional": route.corrected_age_provisional,
        "age_days_used": route.age_days_used,
        "birth_weight_class": E.birth_class(route.birth_weight_g) if route.birth_weight_g is not None else None,
    }


def build_preterm_response(route: Route, ran: dict, warnings: list[str], view: str, pi: E.PretermInput) -> dict:
    r = ran["result"]
    level = r["referral"]["level"]
    reasons = list(r["referral"]["reasons"])
    summary = [f"Preterm or low birth weight baby, {r['pma_weeks']:.1f} weeks post-menstrual age. {LEVEL_PHRASE[level]}"]
    if reasons:
        summary.append("Why: " + "; ".join(reasons[:3]) + ".")
    out = {
        "view": view, "route": route.path,
        "worker_summary": summary,
        "tier": tier_for(level),
        "tier_note": NO_TIER_NOTE if tier_for(level) is None else None,
        "preterm_level": level,
        "reasons": reasons,
        "actions": list(dict.fromkeys(r["referral"]["actions"])),
        "birth_context": birth_context(route),
        "pma_weeks": r["pma_weeks"],
        "birth_classification": r["classification"],
        "measurements": r["measurements"],
        "growth": r.get("growth"),
        "feeding": r["feeding"], "kmc": r["kmc"], "supplements": r["supplements"],
        "handover": r.get("handover"),
        "note": r["referral"]["note"],
        "warnings": list(warnings),
        "rule_set_version": RULE_SET_VERSION,
        "model_version": "none",
        "data_attribution": attribution(),
        "status": None, "disclaimer": DISCLAIMER,
    }
    if view == "audit":
        out["engine_output"] = ran["raw"]
        out["ml_features"] = ml_row(pi)
    return out
