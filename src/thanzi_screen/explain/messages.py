"""English message catalogue (Phase 5). Every message has a stable code so the team can translate (D34).

Wording is a draft for clinician and health-worker review. Plain language, advisory, never diagnostic.
"""
from __future__ import annotations

from ..ml.features import FEATURES

# ---- classification ----
CLASS_PHRASE = {
    "low_risk": "No CMAM malnutrition criterion was met on the measurements entered.",
    "MAM": "Meets the CMAM criterion for moderate acute malnutrition.",
    "SAM_OTP": "Meets the CMAM criterion for severe acute malnutrition.",
    "SAM_INPATIENT": "Meets the CMAM criterion for severe acute malnutrition.",
    "SAM_ASSESS": "Meets the CMAM criterion for severe acute malnutrition.",
    "UNABLE_TO_CLASSIFY": "Could not classify.",
}
INFANT_WFA_PHRASE = "Weight-for-age is very low for an infant under 6 months. A clinician should assess."

# Worker-facing text per rule id. Format fields are filled from the record; missing fields are skipped.
# No HIV wording here (Q7): that appears in the audit trace only.
RULE_WORKER = {
    "SAM.MUAC": "MUAC {muac} cm is below 11.5 cm",
    "SAM.WFLH": "weight-for-length/height z-score {wflh} is below -3",
    "SAM.OEDEMA": "swelling of both feet (oedema {oedema})",
    "MAM.MUAC": "MUAC {muac} cm is from 11.5 up to 12.5 cm",
    "MAM.WFLH": "weight-for-length/height z-score {wflh} is from -3 up to -2",
    "NRU.OEDEMA3": "oedema is +++",
    "NRU.MARASMIC_KWASHIORKOR": "oedema together with severe wasting",
    "NRU.DANGER_SIGNS": "a danger sign is present",
    "NRU.COMPLICATIONS": "a medical complication is present",
    "NRU.APPETITE_FAILED": "the appetite test was failed",
    "OTP.ELIGIBLE": "appetite passed, no complications, well and alert",
    "SAM.ASSESS": "information needed to choose OTP or inpatient care is missing",
    "MAM.HIV_OTP": "meets the conditions for OTP admission",
    "MAM.SFP": "moderate wasting",
    "LOW.NONE": "no CMAM criterion met",
    "INF.WFL": "weight-for-length z-score {wflh} is below -3",
    "INF.OEDEMA": "oedema in an infant under 6 months",
    "INF.VISIBLE_WASTING": "visible severe wasting in an infant under 6 months",
    "INF.TOO_WEAK": "infant is too weak to suckle",
    "INF.NO_GAIN": "infant is not gaining weight",
    "INF.WEIGHT_LT3KG": "weight {weight} kg is below 3.0 kg at 6 months or older",
    "INF.WFA_CLINICIAN": "weight-for-age z-score {wfa} is below -3",
    "DATA.IMPLAUSIBLE_IGNORED": "a z-score looked implausible and was not used",
}

# reasons returned by classify() when it cannot give a final class or needs more information
REASON_TEXT = {
    "wflh_implausible_recheck_measurements": "weight-for-length/height looks implausible: recheck weight and length/height",
    "wfl_implausible_recheck_measurements": "weight-for-length looks implausible: recheck weight and length",
    "no_valid_wasting_measurement": "no valid MUAC or weight-for-length/height",
    "too_weak_to_suckle_not_assessed": "not assessed: too weak to suckle",
    "failure_to_gain_weight_not_assessed": "not assessed: failure to gain weight",
    "visible_severe_wasting_not_assessed": "not assessed: visible severe wasting",
    "appetite_test_not_done": "appetite test not done",
    "danger_signs_not_assessed": "danger signs not assessed",
    "complications_not_assessed": "medical complications not assessed",
    "clinical_status_not_assessed": "'well and alert' not assessed",
    "not_clinically_well_and_alert": "child is not clinically well and alert",
}

# ---- review codes (same text as rules.review.MESSAGES; kept in sync by test) ----
REVIEW_EVIDENCE_LABEL = {
    "unable_to_classify": "The engine could not classify.",
    "missing_assessment": "A severe case is missing assessments.",
    "implausible_value": "A z-score is outside the WHO plausible range.",
    "weight_under_3kg_verify": "Weight is under 3.0 kg at 6 months or older.",
    "discordant_muac_vs_wflh": "MUAC and weight-for-length/height are in different bands.",
    "near_threshold_muac": "MUAC is within the review margin of a cut-off.",
    "near_threshold_z": "Weight-for-length/height z is within the review margin of a cut-off.",
}

# ---- ML features: (kind, text) ; bool kind has (text if 1, text if 0), num kind has one template ----
_B, _N = "bool", "num"
FEATURE_TEXT = {
    "age_months": (_N, "Age is {v:.1f} months"),
    "sex_male": (_B, ("Child is male", "Child is female")),
    "position_height": (_B, ("Measured standing (height)", "Measured lying down (length)")),
    "weight_kg": (_N, "Weight is {v:g} kg"),
    "length_height_cm": (_N, "Length or height is {v:g} cm"),
    "muac_cm": (_N, "MUAC is {v:g} cm"),
    "muac_missing": (_B, ("MUAC was not recorded", "MUAC was recorded")),
    "muac_ge_30": (_B, ("MUAC is 30 cm or more, which is unusual for a child under five", "MUAC is under 30 cm")),
    "muac_unit_suspect": (_B, ("MUAC looks like millimetres entered as centimetres", "MUAC does not look like a millimetre entry")),
    "wfa_z": (_N, "Weight-for-age z-score is {v:.2f}"),
    "lhfa_z": (_N, "Length/height-for-age z-score is {v:.2f}"),
    "wflh_z": (_N, "Weight-for-length/height z-score is {v:.2f}"),
    "wfa_missing": (_B, ("Weight-for-age could not be computed", "Weight-for-age was computed")),
    "lhfa_missing": (_B, ("Length/height-for-age could not be computed", "Length/height-for-age was computed")),
    "wflh_missing": (_B, ("Weight-for-length/height could not be computed", "Weight-for-length/height was computed")),
    "implaus_wfa": (_B, ("Weight-for-age is outside the plausible range", "Weight-for-age is in the plausible range")),
    "implaus_lhfa": (_B, ("Length/height-for-age is outside the plausible range", "Length/height-for-age is in the plausible range")),
    "implaus_wflh": (_B, ("Weight-for-length/height is outside the plausible range", "Weight-for-length/height is in the plausible range")),
    "implaus_count": (_N, "{v:g} of the 3 z-scores are outside the plausible range"),
    "abs_wfa_minus_wflh": (_N, "Weight-for-age and weight-for-length/height z-scores differ by {v:.2f}"),
    "abs_wfa_minus_lhfa": (_N, "Weight-for-age and length/height-for-age z-scores differ by {v:.2f}"),
    "abs_wflh_minus_lhfa": (_N, "Weight-for-length/height and length/height-for-age z-scores differ by {v:.2f}"),
    "length_swap_lhfa_gain": (_N, "Swapping the last two digits of the length changes the length-for-age distance from normal by {v:+.2f} (positive means the swap looks more plausible)"),
    "length_swap_wflh_gain": (_N, "Swapping the last two digits of the length changes the weight-for-length distance from normal by {v:+.2f} (positive means the swap looks more plausible)"),
    "weight_div10_abs_wflh": (_N, "If the weight were 10 times smaller, weight-for-length/height would be {v:.2f} z from the median"),
    "weight_mul10_abs_wflh": (_N, "If the weight were 10 times larger, weight-for-length/height would be {v:.2f} z from the median"),
    "age_dist_6m_days": (_N, "Age is {v:.0f} days from an exact multiple of 6 months"),
    "age_heap_exact": (_B, ("Age is an exact multiple of 6 months (it may be rounded or guessed; ignore this if the date of birth is known)", "Age is not an exact multiple of 6 months")),
    "is_sam": (_B, ("The rules classified the child as severe", "The rules did not classify the child as severe")),
    "is_mam": (_B, ("The rules classified the child as moderate", "The rules did not classify the child as moderate")),
    "is_unable": (_B, ("The rules could not classify the child", "The rules could classify the child")),
    "oedema_present": (_B, ("Oedema was entered", "No oedema was entered")),
    "appetite_not_done": (_B, ("Appetite test not done", "Appetite test done")),
    "danger_unknown": (_B, ("Danger signs not assessed", "Danger signs assessed")),
    "compl_unknown": (_B, ("Medical complications not assessed", "Medical complications assessed")),
    "well_unknown": (_B, ("'Well and alert' not assessed", "'Well and alert' assessed")),
}
assert set(FEATURE_TEXT) == set(FEATURES), "every ML feature needs a plain-language text"

_MISSING_OF = {"wfa_z": "wfa_missing", "lhfa_z": "lhfa_missing", "wflh_z": "wflh_missing", "muac_cm": "muac_missing"}


def feature_phrase(name: str, features: dict) -> str:
    """Plain-language statement of one feature value. Placeholder zeros for missing values are reported as missing."""
    kind, text = FEATURE_TEXT[name]
    v = features[name]
    miss = _MISSING_OF.get(name)
    if miss and features.get(miss):
        return "MUAC was not recorded" if name == "muac_cm" else FEATURE_TEXT[miss][1][0]
    if kind == _B:
        return text[0] if v >= 0.5 else text[1]
    return text.format(v=v)


# ---- action lines for the worker summary ----
OTP_ACTION = "Refer for admission to the Outpatient Therapeutic Programme (OTP)."

# ---- standing notes ----
LIMITS = (
    "Decision support only. Not a diagnosis. A trained clinician makes the final decision.",
    "Flags are advisory and never change the classification.",
    "ML flags were trained on synthetic data only and are not validated on real children.",
    "Wording is a draft pending clinician and health-worker review.",
)
