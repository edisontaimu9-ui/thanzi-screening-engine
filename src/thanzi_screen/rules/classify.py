"""CMAM 2016 classification. Rules decide; nothing here uses ML (D9)."""
from __future__ import annotations

from ..anthro import AnthropometryResult, InputError
from . import rules_v2016 as R
from .models import (
    Appetite, Classification as C, ClassificationResult, ClinicalInputs, OedemaGrade, Tier,
)

IMPLAUSIBLE = "implausible_recheck_measurements"


def _usable_z(ind, warnings: list[str], name: str) -> tuple[float | None, bool]:
    """Return (z or None, ignored_as_implausible)."""
    if ind.status != "ok" or ind.z is None:
        return None, False
    if IMPLAUSIBLE in ind.flags:
        warnings.append(f"{name} z-score flagged implausible and ignored; recheck measurements.")
        return None, True
    return ind.z, False


def _result(c: C, rules, reasons, warnings, programme=None, hiv_otp=False) -> ClassificationResult:
    tier = {
        C.LOW_RISK: Tier.LOW_RISK, C.MAM: Tier.MAM, C.SAM_OTP: Tier.URGENT,
        C.SAM_INPATIENT: Tier.URGENT, C.SAM_ASSESS: Tier.URGENT, C.UNABLE_TO_CLASSIFY: Tier.RECHECK,
    }[c]
    key = "MAM_HIV_OTP" if hiv_otp else {C.LOW_RISK: "LOW_RISK"}.get(c, c.value)
    return ClassificationResult(
        classification=c, tier=tier, programme=programme, rules_fired=tuple(dict.fromkeys(rules)),
        reasons=tuple(reasons), warnings=tuple(warnings), referral_text=R.REFERRAL[key],
        rule_set_version=R.RULE_SET_VERSION, disclaimer=R.DISCLAIMER,
    )


def classify(anthro: AnthropometryResult, clinical: ClinicalInputs) -> ClassificationResult:
    if clinical.muac_cm is not None and not clinical.muac_cm > 0:
        raise InputError("muac_cm must be a positive number")
    warnings: list[str] = list(anthro.warnings)
    oedema = clinical.oedema != OedemaGrade.NONE
    if oedema and anthro.wflh.status == "ok":
        warnings.append("Oedema entered but WFL/H was computed; WFL/H ignored (D14).")
    if (anthro.wfa.status == "ok" and IMPLAUSIBLE in anthro.wfa.flags) or (
            anthro.lhfa.status == "ok" and IMPLAUSIBLE in anthro.lhfa.flags):
        warnings.append("WFA or LHFA flagged implausible; recheck measurements (not a CMAM criterion).")

    infant = anthro.age_months < R.CHILD_PATHWAY_MIN_MONTHS
    if infant:
        return _classify_infant(anthro, clinical, oedema, warnings)
    return _classify_child(anthro, clinical, oedema, warnings)


def _classify_child(anthro, cl: ClinicalInputs, oedema: bool, warnings: list[str]) -> ClassificationResult:
    z, ignored = (None, False) if oedema else _usable_z(anthro.wflh, warnings, "WFL/H")
    m = cl.muac_cm
    rules: list[str] = []
    if ignored:
        rules.append("DATA.IMPLAUSIBLE_IGNORED")

    sev_muac = m is not None and m < R.MUAC_SEVERE_CM
    sev_wfl = z is not None and z < R.WFLH_SEVERE_Z
    mod_muac = m is not None and R.MUAC_SEVERE_CM <= m < R.MUAC_MODERATE_CM
    mod_wfl = z is not None and R.WFLH_SEVERE_Z <= z < R.WFLH_MODERATE_Z
    severe_wasting = sev_muac or sev_wfl
    sam = severe_wasting or oedema

    if sam:
        rules += [r for r, on in (("SAM.MUAC", sev_muac), ("SAM.WFLH", sev_wfl), ("SAM.OEDEMA", oedema)) if on]
        return _classify_sam(cl, severe_wasting, rules, warnings)

    if mod_muac or mod_wfl:
        rules += [r for r, on in (("MAM.MUAC", mod_muac), ("MAM.WFLH", mod_wfl)) if on]
        if (cl.danger_signs or cl.complications):
            warnings.append("Danger signs or complications reported: clinical assessment needed.")
        otp_ready = (cl.appetite == Appetite.PASSED and cl.complications is not None and not cl.complications
                     and _well_alert(cl) is True)
        if cl.hiv_positive:
            if otp_ready:
                rules.append("MAM.HIV_OTP")
                return _result(C.MAM, rules, [], warnings, programme="OTP", hiv_otp=True)
            warnings.append("HIV-positive with MAM: OTP admission needs appetite test passed, no complications, "
                            "clinically well and alert. Not confirmed; assess for OTP.")
        rules.append("MAM.SFP")
        return _result(C.MAM, rules, [], warnings, programme="SFP")

    # No criterion met. Low risk only on a valid wasting assessment (Q1, never low risk by default).
    reasons = []
    if ignored:
        reasons.append("wflh_implausible_recheck_measurements")
    if m is None and z is None:
        reasons.append("no_valid_wasting_measurement")
    if reasons:
        return _result(C.UNABLE_TO_CLASSIFY, rules, reasons, warnings)
    if m is None:
        warnings.append("MUAC not provided; classified on WFL/H only.")
    return _result(C.LOW_RISK, rules + ["LOW.NONE"], [], warnings)


def _well_alert(cl: ClinicalInputs) -> bool | None:
    from .models import DangerSign
    if cl.danger_signs and (DangerSign.LETHARGY_NOT_ALERT in cl.danger_signs
                            or DangerSign.UNCONSCIOUSNESS in cl.danger_signs):
        return False
    return cl.clinically_well_and_alert


def _classify_sam(cl: ClinicalInputs, severe_wasting: bool, rules: list[str], warnings: list[str]):
    g = cl.oedema
    oedema = g != OedemaGrade.NONE
    nru: list[str] = []
    if g == OedemaGrade.PLUS_PLUS_PLUS:
        nru.append("NRU.OEDEMA3")
    if oedema and severe_wasting:
        nru.append("NRU.MARASMIC_KWASHIORKOR")
    if cl.danger_signs:
        nru.append("NRU.DANGER_SIGNS")
    if cl.complications:
        nru.append("NRU.COMPLICATIONS")
    if cl.appetite == Appetite.FAILED:
        nru.append("NRU.APPETITE_FAILED")
    if nru:
        return _result(C.SAM_INPATIENT, rules + nru, [], warnings, programme="NRU")

    wa = _well_alert(cl)
    missing = []
    if cl.appetite == Appetite.NOT_DONE:
        missing.append("appetite_test_not_done")
    if cl.danger_signs is None:
        missing.append("danger_signs_not_assessed")
    if cl.complications is None:
        missing.append("complications_not_assessed")
    if wa is None:
        missing.append("clinical_status_not_assessed")
    elif wa is False:
        missing.append("not_clinically_well_and_alert")
    if missing:
        return _result(C.SAM_ASSESS, rules + ["SAM.ASSESS"], missing, warnings)
    return _result(C.SAM_OTP, rules + ["OTP.ELIGIBLE"], [], warnings, programme="OTP")


def _classify_infant(anthro, cl: ClinicalInputs, oedema: bool, warnings: list[str]) -> ClassificationResult:
    if cl.muac_cm is not None:
        warnings.append("MUAC is not used under 6 months and was ignored (D2).")
    z, ignored = (None, False) if oedema else _usable_z(anthro.wflh, warnings, "WFL")
    rules: list[str] = ["DATA.IMPLAUSIBLE_IGNORED"] if ignored else []
    length = anthro.length_height_used_cm

    hit: list[str] = []
    if z is not None and length >= R.INFANT_WFL_MIN_LENGTH_CM and z < R.WFLH_SEVERE_Z:
        hit.append("INF.WFL")
    if oedema:
        hit.append("INF.OEDEMA")
    if cl.visible_severe_wasting:
        hit.append("INF.VISIBLE_WASTING")
    if cl.too_weak_to_suckle:
        hit.append("INF.TOO_WEAK")
    if cl.failure_to_gain_weight:
        hit.append("INF.NO_GAIN")
    if hit:
        return _result(C.SAM_INPATIENT, rules + hit, [], warnings, programme="NRU")

    wfa_z, _ = _usable_z(anthro.wfa, warnings, "WFA")
    if wfa_z is not None and wfa_z < R.INFANT_WFA_REFER_Z:
        return _result(C.MAM, rules + ["INF.WFA_CLINICIAN"], [], warnings, programme=None)

    reasons = []
    if ignored:
        reasons.append("wfl_implausible_recheck_measurements")
    if cl.too_weak_to_suckle is None:
        reasons.append("too_weak_to_suckle_not_assessed")
    if cl.failure_to_gain_weight is None:
        reasons.append("failure_to_gain_weight_not_assessed")
    if length < R.INFANT_WFL_MIN_LENGTH_CM and cl.visible_severe_wasting is None:
        reasons.append("visible_severe_wasting_not_assessed")
    if reasons:
        return _result(C.UNABLE_TO_CLASSIFY, rules, reasons, warnings)
    return _result(C.LOW_RISK, rules + ["LOW.NONE"], [], warnings)
