"""ML target B ground truth: why a record should be reviewed by a clinician.

Constructed deterministically from the engine outputs, so a model can only learn this
function, not clinical truth. Margins are ASSUMPTIONS (config).
"""
from __future__ import annotations

IMPLAUSIBLE = "implausible_recheck_measurements"


def _band(value: float, severe: float, moderate: float) -> str:
    return "severe" if value < severe else ("moderate" if value < moderate else "normal")


def review_reasons(anthro, result, muac, oedema: bool, cfg) -> list[str]:
    reasons: list[str] = []
    cls = result.classification.value
    if cls == "UNABLE_TO_CLASSIFY":
        reasons.append("unable_to_classify")
    if cls == "SAM_ASSESS":
        reasons.append("missing_assessment")
    if any(i.status == "ok" and IMPLAUSIBLE in i.flags for i in (anthro.wfa, anthro.lhfa, anthro.wflh)):
        reasons.append("implausible_value")
    if "INF.WEIGHT_LT3KG" in result.rules_fired:
        reasons.append("weight_under_3kg_verify")
    z = anthro.wflh.z if anthro.wflh.status == "ok" and IMPLAUSIBLE not in anthro.wflh.flags and not oedema else None
    if muac is not None and z is not None and _band(muac, 11.5, 12.5) != _band(z, -3.0, -2.0):
        reasons.append("discordant_muac_vs_wflh")
    if muac is not None and (abs(muac - 11.5) <= cfg.review_muac_margin_cm or abs(muac - 12.5) <= cfg.review_muac_margin_cm):
        reasons.append("near_threshold_muac")
    if z is not None and (abs(z + 3) <= cfg.review_z_margin or abs(z + 2) <= cfg.review_z_margin):
        reasons.append("near_threshold_z")
    return reasons
