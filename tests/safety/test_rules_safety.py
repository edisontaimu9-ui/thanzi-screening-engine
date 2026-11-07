"""Safety invariants for the rules (D9 seed): no output less urgent than the most severe criterion met."""
import itertools

from thanzi_screen.rules import Appetite, Classification as C, ClinicalInputs, OedemaGrade as O, Tier, classify
from tests.rules.test_classify import _A

RANK = {Tier.LOW_RISK: 0, Tier.RECHECK: 1, Tier.MAM: 1, Tier.URGENT: 2}


def test_never_less_urgent_than_most_severe_single_criterion():
    for muac, z, oed, app in itertools.product(
            (None, 10.0, 11.5, 12.0, 13.0), (-4.0, -3.0, -2.5, 0.0), list(O), list(Appetite)):
        r = classify(_A(z), ClinicalInputs(muac_cm=muac, oedema=oed, appetite=app))
        oedema_on = oed != O.NONE
        sam = oedema_on or (muac is not None and muac < 11.5) or (not oedema_on and z < -3)
        mam = (muac is not None and muac < 12.5) or (not oedema_on and z < -2)
        if sam:
            assert r.tier == Tier.URGENT
        elif mam:
            assert r.tier in (Tier.MAM, Tier.URGENT)
        # Never low risk when any criterion is met
        if sam or mam:
            assert r.classification != C.LOW_RISK


def test_sam_never_otp_without_complete_information():
    for kw in (dict(), dict(appetite=Appetite.PASSED), dict(appetite=Appetite.PASSED, danger_signs=frozenset())):
        r = classify(_A(0.0), ClinicalInputs(muac_cm=11.0, **kw))
        assert r.classification != C.SAM_OTP
