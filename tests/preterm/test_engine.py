import math
from thanzi_screen.preterm import screen, z_for, features, PretermInput

def test_lms_median_is_z0():
    r = z_for("girls", "weight", 22.5, 470.8745453403287)
    assert r["z"] == 0 and r["percentile"] == 50

def test_both_sexes_and_measures():
    for s in ("girls", "boys"):
        for m, v in (("weight", 1500), ("length", 40), ("hc", 28)):
            assert z_for(s, m, 30.0, v) is not None

def test_matches_js_reference():
    r = screen(PretermInput(sex="f", ga_weeks=29, birth_weight_g=1100, age_days=20, weight_g=1250,
                            length_cm=38, hc_cm=27, gaining_days=2))
    assert r["measurements"]["weight"]["z"] == -1.99
    assert r["measurements"]["birth_weight"]["z"] == -0.68
    assert r["growth"]["weight"]["z_change"] == -1.31 and r["growth"]["weight"]["tier"] == "moderate"
    assert r["feeding"]["ml_per_feed"] == 19 and r["kmc"] == "facility"
    assert r["referral"]["level"] == "refer"

def test_late_preterm_follow_up_only():
    r = screen(PretermInput(sex="m", ga_weeks=34, birth_weight_g=2100, age_days=3, weight_g=2000))
    assert r["referral"]["level"] == "follow_up"

def test_outside_range_handover():
    r = screen(PretermInput(sex="f", ga_weeks=30, birth_weight_g=1300, age_days=150, weight_g=4000))
    assert "handover" in r and r["measurements"]["weight"] == "outside_fenton_range"

def test_features_numeric():
    f = features(PretermInput(sex="m", ga_weeks=28, birth_weight_g=1000, age_days=10, weight_g=1000))
    assert all(isinstance(v, float) or isinstance(v, int) for v in f.values())
    assert math.isnan(f["z_length"])


def base(**k):
    d = dict(sex="f", ga_weeks=29, birth_weight_g=1100, age_days=20, weight_g=1250)
    d.update(k); return PretermInput(**d)

def test_growth_alone_never_urgent():
    r = screen(base(weight_g=900, length_cm=30, hc_cm=22, birth_length_cm=36, birth_hc_cm=26, birth_weight_g=1100))
    assert r["referral"]["level"] != "urgent_refer"

def test_urgent_triggers():
    assert screen(base(bilious_vomiting=True))["referral"]["level"] == "urgent_refer"
    assert screen(base(abdominal_distension=True))["referral"]["level"] != "urgent_refer"
    assert screen(base(abdominal_distension=True, blood_in_stool=True))["referral"]["level"] == "urgent_refer"
    assert screen(base(cannot_feed=True, lethargic=True))["referral"]["level"] == "urgent_refer"
    r = screen(base(convulsions=True))
    assert any("antibiotics" in a for a in r["referral"]["actions"])

def test_mild_tier_follow_up():
    r = screen(base(weight_g=1450))  # small z drop vs birth -> not a refer by growth alone
    assert r["referral"]["level"] in ("follow_up", "routine")

def test_two_measures_escalate():
    r = screen(base(length_cm=34, hc_cm=24, birth_length_cm=37, birth_hc_cm=26.5))
    assert r["referral"]["level"] == "refer"
