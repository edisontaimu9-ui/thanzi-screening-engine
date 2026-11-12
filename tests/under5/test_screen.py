import pytest

from thanzi_screen.factors import ChildRecord, Demographic, FactorError, Visit, completeness
from thanzi_screen.rules import OedemaGrade
from thanzi_screen.under5 import analyse_growth, compute_panel, screen_record
from thanzi_screen.under5.longitudinal import FalteringConfig


def visit(age, w, l, muac=None, pos=None, oedema=OedemaGrade.NONE, **kw):
    pos = pos or ("length" if age <= 730 else "height")
    return Visit(age, w, l, pos, muac_cm=muac, oedema=oedema, **kw)


def rec(visits, sex="male", **kw):
    return ChildRecord(sex, tuple(visits), **kw)


def test_panel_normal_child():
    p = compute_panel("male", visit(500, 10.9, 82.0, 14.0))
    assert p.waz.status == p.haz.status == p.whz.status == "normal"
    assert p.muac.category == "normal" and p.muac.z_for_age is None
    assert p.wasting_and_stunting is False


def test_panel_wasted_and_stunted_and_muac_cutoffs():
    p = compute_panel("female", visit(600, 6.6, 72.0, 11.0))
    assert p.whz.status in ("moderate", "severe") and p.haz.status in ("moderate", "severe")
    assert p.wasting_and_stunting is True
    assert p.muac.category == "severe"
    assert compute_panel("female", visit(600, 9.0, 80.0, 11.5)).muac.category == "moderate"
    assert compute_panel("female", visit(600, 9.0, 80.0, 12.5)).muac.category == "normal"


def test_muac_not_applicable_under_six_months_and_missing_is_not_normal():
    assert compute_panel("male", visit(100, 6.0, 60.0, 13.0)).muac.category == "not_applicable_under_6_months"
    assert compute_panel("male", visit(500, 10.0, 80.0)).muac.category == "not_measured"


def test_oedema_withholds_weight_indicators():
    p = compute_panel("male", visit(500, 11.0, 80.0, 12.0, oedema=OedemaGrade.PLUS_PLUS))
    assert p.oedema.present and p.oedema.weight_indicators_withheld
    assert p.waz.status == "not_assessable" and p.whz.status == "not_assessable"
    assert p.wasting_and_stunting is None
    assert p.haz.status != "not_assessable"


def test_single_visit_not_assessable_never_none():
    r = analyse_growth(rec([visit(500, 10.0, 80.0, 13.0)]))
    assert r.level == "not_assessable" and not r.growth_faltering
    assert "fewer_than_two_usable_visits" in r.reasons


def test_steady_growth_is_none():
    r = analyse_growth(rec([visit(365, 9.6, 74.5, 14), visit(456, 10.3, 78.0, 14), visit(548, 10.9, 81.0, 14)]))
    assert r.level == "none" and not r.growth_faltering


def test_weight_loss_is_possible_then_sustained():
    one = analyse_growth(rec([visit(365, 9.6, 74.5, 14), visit(456, 9.0, 78.0, 13.5)]))
    assert one.weight_faltering == "possible" and one.growth_faltering
    two = analyse_growth(rec([visit(365, 9.6, 74.5, 14), visit(456, 9.0, 78.0, 13.5), visit(548, 8.4, 80.0, 13)]))
    assert two.weight_faltering == "sustained" and two.level == "sustained"


def test_short_and_long_intervals_are_not_judged():
    short = analyse_growth(rec([visit(365, 9.6, 74.5), visit(380, 8.0, 74.8)]))
    assert short.level == "not_assessable" and any(x.startswith("interval_too_short") for x in short.reasons)
    long_ = analyse_growth(rec([visit(200, 7.5, 67.0), visit(700, 9.0, 80.0)]))
    assert long_.level == "not_assessable" and any(x.startswith("interval_too_long") for x in long_.reasons)


def test_implausible_visit_excluded_not_used():
    r = analyse_growth(rec([visit(365, 9.6, 74.5), visit(456, 96.0 / 10 * 4, 78.0), visit(548, 10.9, 81.0)]))
    assert r.visits_excluded and r.visits_excluded[0]["age_days"] == 456


def test_linear_faltering_flag():
    r = analyse_growth(rec([visit(365, 9.6, 74.5), visit(456, 10.0, 75.0)]))
    assert r.linear_faltering == "possible"


def test_config_changes_threshold():
    v = [visit(365, 9.6, 74.5), visit(456, 10.2, 78.0)]
    strict = analyse_growth(rec(v), FalteringConfig(fall_sd=0.1))
    assert strict.config.fall_sd == 0.1


def test_screen_matches_rules_and_reports_completeness():
    r = rec([visit(500, 7.0, 76.0, 11.0, appetite=None) if False else visit(500, 7.0, 76.0, 11.0)],
            demographic=Demographic(birth_weight_g=2000))
    s = screen_record(r).to_dict()
    assert s["module"] == "deterministic_screening"
    assert s["classification"]["classification"].startswith("SAM")
    assert any("corrected age" in w for w in s["warnings"])
    assert s["factor_completeness"]["feeding"]["status"] == "none_assessed"


def test_validation_rejects_impossible_and_duplicates():
    with pytest.raises(FactorError):
        Visit(500, -1.0, 80.0, "length")
    with pytest.raises(FactorError):
        Visit(500, 10.0, 80.0, "sitting")
    with pytest.raises(FactorError):
        rec([visit(500, 10.0, 80.0), visit(500, 10.1, 80.2)])
    with pytest.raises(FactorError):
        ChildRecord("other", (visit(500, 10.0, 80.0),))
    with pytest.raises(FactorError):
        Demographic(multiple_birth="yes")


def test_visits_sorted_and_completeness_counts():
    r = rec([visit(548, 10.9, 81.0), visit(365, 9.6, 74.5)])
    assert [v.age_days for v in r.visits] == [365, 548]
    assert completeness(r)["demographic"]["assessed"] == 0
