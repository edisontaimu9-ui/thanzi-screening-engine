"""Rules-based review flag (ML target B, implemented as rules per Edison, D45).

Deterministic and explainable. Advisory only: it never changes a classification.
Margins are ASSUMPTIONS (D40).
"""
from __future__ import annotations

from dataclasses import dataclass

IMPLAUSIBLE = "implausible_recheck_measurements"
REVIEW_MUAC_MARGIN_CM = 0.2
REVIEW_Z_MARGIN = 0.1
SOURCE = "rules_review_v1"

MESSAGES = {
    "unable_to_classify": "Could not classify. Recheck the measurements or complete the missing assessments.",
    "missing_assessment": "Severe case with missing assessments. A clinician should decide OTP or inpatient care.",
    "implausible_value": "A measurement looks implausible. Recheck weight, length or height and age.",
    "weight_under_3kg_verify": "Weight is under 3.0 kg at 6 months or older. Verify the measurement.",
    "discordant_muac_vs_wflh": "MUAC and weight-for-length/height point to different severity. Review the case.",
    "near_threshold_muac": "MUAC is very close to a cut-off. Recheck it and review the case.",
    "near_threshold_z": "Weight-for-length/height is very close to a cut-off. Recheck and review the case.",
}


@dataclass(frozen=True)
class ReviewResult:
    needed: bool
    reasons: tuple[str, ...]
    messages: tuple[str, ...]
    source: str = SOURCE


def _band(value: float, severe: float, moderate: float) -> str:
    return "severe" if value < severe else ("moderate" if value < moderate else "normal")


def review(anthro, result, muac, oedema: bool, muac_margin: float = REVIEW_MUAC_MARGIN_CM,
           z_margin: float = REVIEW_Z_MARGIN) -> ReviewResult:
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
    if muac is not None and (abs(muac - 11.5) <= muac_margin or abs(muac - 12.5) <= muac_margin):
        reasons.append("near_threshold_muac")
    if z is not None and (abs(z + 3) <= z_margin or abs(z + 2) <= z_margin):
        reasons.append("near_threshold_z")
    return ReviewResult(bool(reasons), tuple(reasons), tuple(MESSAGES[r] for r in reasons))
