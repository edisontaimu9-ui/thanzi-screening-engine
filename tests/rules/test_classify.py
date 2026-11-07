import pytest

from thanzi_screen.anthro import InputError, compute_anthropometry
from thanzi_screen.rules import (
    Appetite, Classification as C, ClinicalInputs, Complication, DangerSign, OedemaGrade as O, Tier,
    RULES, classify,
)
from thanzi_screen.rules.rules_v2016 import DISCLAIMER


def anthro(age_days=300, weight=8.6, length=70.0, oedema=False, sex="male"):
    return compute_anthropometry(sex=sex, weight_kg=weight, length_height_cm=length,
                                 measure_position="length" if age_days <= 730 else "height",
                                 age_days=age_days, oedema=oedema)


NORMAL = anthro()  # ~ median child, 10 months
FULL = dict(appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset(),
            clinically_well_and_alert=True)


def cls(a, **kw):
    return classify(a, ClinicalInputs(**kw))


# ---- MUAC boundaries (D5) ----
@pytest.mark.parametrize("m,expected", [
    (11.4, C.SAM_OTP), (11.49, C.SAM_OTP), (11.5, C.MAM), (12.49, C.MAM), (12.5, C.LOW_RISK), (14.0, C.LOW_RISK)])
def test_muac_boundaries(m, expected):
    assert cls(NORMAL, muac_cm=m, **FULL).classification == expected


def test_muac_invalid():
    with pytest.raises(InputError):
        cls(NORMAL, muac_cm=0)
    with pytest.raises(InputError):
        cls(NORMAL, muac_cm=-1)


# ---- WFL/H boundaries via stubbed z ----
class _Ind:
    def __init__(self, z, flags=(), status="ok"):
        self.z, self.flags, self.status = z, flags, status


class _A:
    def __init__(self, z, flags=(), age_months=10.0, length=70.0, wfa=None, status="ok"):
        self.wflh = _Ind(z, flags, status)
        self.wfa = wfa or _Ind(0.0)
        self.lhfa = _Ind(0.0)
        self.age_months, self.length_height_used_cm, self.warnings = age_months, length, ()


@pytest.mark.parametrize("z,expected", [
    (-3.01, C.SAM_OTP), (-3.0, C.MAM), (-2.01, C.MAM), (-2.0, C.LOW_RISK), (0.0, C.LOW_RISK)])
def test_wflh_boundaries(z, expected):
    assert cls(_A(z), **FULL).classification == expected


# ---- oedema ----
def test_oedema_grades():
    a = anthro(oedema=True)
    assert cls(a, oedema=O.PLUS, **FULL).classification == C.SAM_OTP
    assert cls(a, oedema=O.PLUS_PLUS, **FULL).classification == C.SAM_OTP
    r = cls(a, oedema=O.PLUS_PLUS_PLUS, **FULL)
    assert r.classification == C.SAM_INPATIENT and "NRU.OEDEMA3" in r.rules_fired


def test_oedema_with_severe_muac_is_inpatient():
    r = cls(anthro(oedema=True), oedema=O.PLUS, muac_cm=11.0, **FULL)
    assert r.classification == C.SAM_INPATIENT and "NRU.MARASMIC_KWASHIORKOR" in r.rules_fired


def test_oedema_wflh_ignored_not_used_as_wasting():
    # Oedema with normal MUAC: WFL/H not computed (D14), so no marasmic kwashiorkor.
    r = cls(anthro(oedema=True), oedema=O.PLUS, muac_cm=13.0, **FULL)
    assert r.classification == C.SAM_OTP


def test_oedema_but_wflh_computed_warns_and_ignores():
    r = cls(_A(-4.0), oedema=O.PLUS, **FULL)
    assert r.classification == C.SAM_OTP and "SAM.WFLH" not in r.rules_fired
    assert any("D14" in w for w in r.warnings)


# ---- inpatient triggers ----
@pytest.mark.parametrize("kw,rule", [
    (dict(danger_signs=frozenset({DangerSign.CONVULSIONS})), "NRU.DANGER_SIGNS"),
    (dict(complications=frozenset({Complication.MALARIA})), "NRU.COMPLICATIONS"),
    (dict(appetite=Appetite.FAILED), "NRU.APPETITE_FAILED"),
])
def test_inpatient_triggers(kw, rule):
    base = {**FULL, **kw}
    r = cls(NORMAL, muac_cm=11.0, **base)
    assert r.classification == C.SAM_INPATIENT and rule in r.rules_fired and r.programme == "NRU"
    assert r.tier == Tier.URGENT


@pytest.mark.parametrize("sign", list(DangerSign))
def test_every_danger_sign_sends_sam_to_inpatient(sign):
    r = cls(NORMAL, muac_cm=11.0, **{**FULL, "danger_signs": frozenset({sign})})
    assert r.classification == C.SAM_INPATIENT


@pytest.mark.parametrize("comp", list(Complication))
def test_every_complication_sends_sam_to_inpatient(comp):
    r = cls(NORMAL, muac_cm=11.0, **{**FULL, "complications": frozenset({comp})})
    assert r.classification == C.SAM_INPATIENT


def test_failed_appetite_not_sam_does_not_escalate():
    r = cls(NORMAL, muac_cm=13.0, **{**FULL, "appetite": Appetite.FAILED})
    assert r.classification == C.LOW_RISK


# ---- Q3 missing info never defaults to OTP ----
@pytest.mark.parametrize("missing", ["appetite", "danger_signs", "complications", "clinically_well_and_alert"])
def test_missing_info_is_assess_not_otp(missing):
    kw = dict(FULL)
    kw[missing] = Appetite.NOT_DONE if missing == "appetite" else None
    r = cls(NORMAL, muac_cm=11.0, **kw)
    assert r.classification == C.SAM_ASSESS and r.tier == Tier.URGENT and r.reasons


def test_not_clinically_well_is_assess():
    r = cls(NORMAL, muac_cm=11.0, **{**FULL, "clinically_well_and_alert": False})
    assert r.classification == C.SAM_ASSESS


def test_known_nru_trigger_beats_missing_info():
    r = cls(NORMAL, muac_cm=11.0, oedema=O.PLUS_PLUS_PLUS)
    assert r.classification == C.SAM_INPATIENT


# ---- HIV rule ----
def test_hiv_mam_to_otp():
    r = cls(NORMAL, muac_cm=12.0, hiv_positive=True, **FULL)
    assert r.classification == C.MAM and r.programme == "OTP" and "MAM.HIV_OTP" in r.rules_fired


def test_hiv_mam_without_otp_conditions_stays_sfp_with_warning():
    r = cls(NORMAL, muac_cm=12.0, hiv_positive=True)
    assert r.programme == "SFP" and r.warnings


def test_hiv_does_not_change_low_risk_or_sam():
    assert cls(NORMAL, muac_cm=13.0, hiv_positive=True, **FULL).classification == C.LOW_RISK
    assert cls(NORMAL, muac_cm=11.0, hiv_positive=True, **FULL).classification == C.SAM_OTP


# ---- Q1 implausible handling ----
def test_implausible_wflh_ignored_valid_muac_severe_still_sam():
    r = cls(_A(-5.5, flags=("implausible_recheck_measurements",)), muac_cm=11.0, **FULL)
    assert r.classification == C.SAM_OTP and "SAM.WFLH" not in r.rules_fired


def test_implausible_wflh_normal_muac_never_low_risk():
    r = cls(_A(6.0, flags=("implausible_recheck_measurements",)), muac_cm=13.0, **FULL)
    assert r.classification == C.UNABLE_TO_CLASSIFY and r.tier == Tier.RECHECK


def test_implausible_wflh_no_muac_is_unable():
    r = cls(_A(-7.0, flags=("implausible_recheck_measurements",)), **FULL)
    assert r.classification == C.UNABLE_TO_CLASSIFY


def test_no_valid_measurement_is_unable():
    r = cls(_A(None, status="not_computable"), **FULL)
    assert r.classification == C.UNABLE_TO_CLASSIFY


def test_oedema_with_implausible_wflh_still_sam():
    r = cls(_A(-6.0, flags=("implausible_recheck_measurements",)), oedema=O.PLUS, **FULL)
    assert r.classification == C.SAM_OTP


# ---- 6 month boundary (Q5), MUAC under 6 months (Q6) ----
def test_exactly_six_months_is_child_pathway():
    a = _A(0.0, age_months=6.0)
    r = cls(a, muac_cm=11.0, **FULL)
    assert r.classification == C.SAM_OTP


def test_muac_ignored_under_six_months_with_warning():
    a = _A(0.0, age_months=4.0, length=60.0)
    r = cls(a, muac_cm=10.0, too_weak_to_suckle=False, failure_to_gain_weight=False)
    assert r.classification == C.LOW_RISK and any("MUAC" in w for w in r.warnings)


# ---- infants ----
INF = dict(too_weak_to_suckle=False, failure_to_gain_weight=False)


def test_infant_wfl_severe():
    assert cls(_A(-3.5, age_months=3, length=58.0), **INF).classification == C.SAM_INPATIENT


def test_infant_wfl_not_applied_below_45cm():
    r = cls(_A(-3.5, age_months=1, length=44.0), visible_severe_wasting=False, **INF)
    assert r.classification == C.LOW_RISK


@pytest.mark.parametrize("kw,rule", [
    (dict(visible_severe_wasting=True), "INF.VISIBLE_WASTING"),
    (dict(too_weak_to_suckle=True), "INF.TOO_WEAK"),
    (dict(failure_to_gain_weight=True), "INF.NO_GAIN"),
])
def test_infant_clinical_triggers(kw, rule):
    base = {**INF, "visible_severe_wasting": False, **kw}
    r = cls(_A(0.0, age_months=2, length=50.0), **base)
    assert r.classification == C.SAM_INPATIENT and rule in r.rules_fired


def test_infant_oedema():
    r = cls(_A(0.0, age_months=2, length=50.0), oedema=O.PLUS, **INF)
    assert r.classification == C.SAM_INPATIENT and "INF.OEDEMA" in r.rules_fired


def test_infant_wfa_below_minus3_is_clinician_referral():
    r = cls(_A(0.0, age_months=3, length=58.0, wfa=_Ind(-3.5)), **INF)
    assert r.classification == C.MAM and "INF.WFA_CLINICIAN" in r.rules_fired


def test_infant_missing_inputs_never_low_risk():
    r = cls(_A(0.0, age_months=3, length=58.0))
    assert r.classification == C.UNABLE_TO_CLASSIFY and r.reasons
    r2 = cls(_A(0.0, age_months=1, length=44.0), **INF)
    assert "visible_severe_wasting_not_assessed" in r2.reasons


# ---- output contract ----
@pytest.mark.parametrize("kw", [
    dict(muac_cm=13.0), dict(muac_cm=12.0), dict(muac_cm=11.0), dict(muac_cm=11.0, **FULL), dict()])
def test_every_output_has_contract(kw):
    r = cls(NORMAL, **kw)
    assert r.disclaimer == DISCLAIMER and r.rule_set_version == "rules_v2016" and r.referral_text
    assert all(i in RULES for i in r.rules_fired)
    for i in r.rules_fired:
        assert RULES[i].source and RULES[i].page and RULES[i].tag in {"DOCUMENTED", "ASSUMPTION", "RECOMMENDATION"}


def test_real_anthro_integration_severe_wasting():
    a = anthro(weight=6.0, length=68.0)  # z about -3.6
    r = cls(a, **FULL)
    assert r.classification == C.SAM_OTP and "SAM.WFLH" in r.rules_fired
