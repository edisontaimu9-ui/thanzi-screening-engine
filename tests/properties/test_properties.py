"""Property and invariant tests on the full pipeline (anthropometry, then rules). Phase 7 (D93).

Deterministic grids, standard library only. These check relationships that must hold for every
input (more severe input never gives a less urgent tier, missing information never lowers urgency,
output invariants), not single expected values. A failure here is a finding to decide in the
decision log, not something to patch silently.
"""
import itertools

from thanzi_screen.anthro import InputError, compute_anthropometry
from thanzi_screen.rules import (
    RULES, Appetite, Classification as C, ClinicalInputs, Complication, DangerSign, OedemaGrade as O, Tier, classify,
)
from thanzi_screen.rules.rules_v2016 import DISCLAIMER, RULE_SET_VERSION

URGENCY = {Tier.LOW_RISK: 0, Tier.MAM: 1, Tier.RECHECK: 2, Tier.URGENT: 3}   # recheck is never less urgent than MAM
FULL = dict(appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset(), clinically_well_and_alert=True)


def anthro(age_days=300, weight=8.6, length=70.0, sex="male", oedema=False):
    return compute_anthropometry(sex=sex, weight_kg=weight, length_height_cm=length,
                                 measure_position="length" if age_days <= 730 else "height",
                                 age_days=age_days, oedema=oedema)


def urgency(a, **kw):
    return URGENCY[classify(a, ClinicalInputs(**kw)).tier]


def test_lower_muac_is_never_less_urgent():
    for sex, age in itertools.product(("male", "female"), (200, 300, 600, 1200)):
        a = anthro(age_days=age, sex=sex, length=70.0 if age <= 730 else 95.0, weight=8.6 if age <= 730 else 14.0)
        levels = [urgency(a, muac_cm=m, **FULL) for m in (14.0, 13.0, 12.6, 12.4, 12.0, 11.6, 11.4, 10.0, 8.0)]
        assert levels == sorted(levels), (sex, age, levels)


def test_higher_oedema_grade_is_never_less_urgent():
    for sex, age in itertools.product(("male", "female"), (200, 600, 1200)):
        for kw in (dict(muac_cm=13.0, **FULL), dict(muac_cm=11.0, **FULL), dict(muac_cm=None)):
            levels = [urgency(anthro(age_days=age, sex=sex, oedema=g != O.NONE), oedema=g, **kw) for g in O]
            assert levels == sorted(levels), (sex, age, kw, levels)


def test_oedema_plus_plus_plus_is_inpatient_for_children_over_six_months():
    for age in (200, 600, 1200):
        r = classify(anthro(age_days=age, oedema=True), ClinicalInputs(oedema=O.PLUS_PLUS_PLUS, muac_cm=13.0, **FULL))
        assert r.classification == C.SAM_INPATIENT, age


def test_adding_a_danger_sign_or_complication_is_never_less_urgent():
    a = anthro()
    for muac in (13.0, 12.0, 11.0):
        base = urgency(a, muac_cm=muac, **FULL)
        for ds in DangerSign:
            assert urgency(a, muac_cm=muac, **{**FULL, "danger_signs": frozenset({ds})}) >= base, (muac, ds)
        for cp in Complication:
            assert urgency(a, muac_cm=muac, **{**FULL, "complications": frozenset({cp})}) >= base, (muac, cp)


def test_sam_with_any_danger_sign_or_complication_is_never_outpatient():
    a = anthro()
    for ds in DangerSign:
        r = classify(a, ClinicalInputs(muac_cm=11.0, **{**FULL, "danger_signs": frozenset({ds})}))
        assert r.classification == C.SAM_INPATIENT, ds
    for cp in Complication:
        r = classify(a, ClinicalInputs(muac_cm=11.0, **{**FULL, "complications": frozenset({cp})}))
        assert r.classification == C.SAM_INPATIENT, cp


def test_missing_information_is_never_less_urgent_than_assessed_absent():
    a = anthro()
    for muac in (None, 13.0, 12.0, 11.0):
        known = urgency(a, muac_cm=muac, **FULL)
        for field, unknown in (("danger_signs", None), ("complications", None),
                               ("clinically_well_and_alert", None), ("appetite", Appetite.NOT_DONE)):
            got = urgency(a, muac_cm=muac, **{**FULL, field: unknown})
            assert got >= known, (muac, field, got, known)


def test_lower_weight_is_never_less_urgent_when_not_flagged_implausible():
    for sex, age, length in itertools.product(("male", "female"), (200, 300, 600), (62.0, 70.0, 78.0)):
        levels = []
        for w in (11.0, 10.0, 9.0, 8.0, 7.0, 6.5, 6.0, 5.5):
            a = anthro(age_days=age, sex=sex, length=length, weight=w)
            if "implausible_recheck_measurements" in a.wflh.flags:
                continue
            levels.append(urgency(a, **FULL))
        assert levels == sorted(levels), (sex, age, length, levels)


def test_output_invariants_over_a_wide_sweep():
    n = 0
    for sex, age, w, muac, oed, app in itertools.product(
            ("male", "female"), (20, 100, 179, 183, 300, 700, 1200), (2.4, 4.0, 6.5, 9.0, 12.0),
            (None, 10.0, 11.5, 12.0, 13.0), list(O), list(Appetite)):
        length = 50.0 if age < 183 else (70.0 if age <= 730 else 95.0)
        try:
            a = anthro(age_days=age, weight=w, length=length, sex=sex, oedema=oed != O.NONE)
        except InputError:
            continue
        r = classify(a, ClinicalInputs(muac_cm=muac, oedema=oed, appetite=app))
        n += 1
        assert set(r.rules_fired) <= set(RULES), r.rules_fired
        if not r.rules_fired:                                   # by design: unable to classify carries reasons, not rules
            assert r.classification == C.UNABLE_TO_CLASSIFY and r.reasons, r
        assert r.referral_text and r.disclaimer == DISCLAIMER and r.rule_set_version == RULE_SET_VERSION
        if r.tier == Tier.URGENT:
            assert "urgent" in r.referral_text.lower()
        assert r == classify(a, ClinicalInputs(muac_cm=muac, oedema=oed, appetite=app))   # deterministic
    assert n > 500
