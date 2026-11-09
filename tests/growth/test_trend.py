"""Growth trends across two visits (R4, R5, R20, guide R21). Synthetic inputs only; the Fadi case is the WHO guide's own (p. 43)."""
import ast
import random
from pathlib import Path

import pytest

from thanzi_screen.anthro import compute_anthropometry, engine as anthro_engine
from thanzi_screen.growth import MIN_INTERVAL_DAYS, PreviousVisit, assess_trends, trend as T

SRC = Path(__file__).resolve().parents[2] / "src" / "thanzi_screen"


def _by_name(t):
    return {i.indicator: i for i in t.indicators}


def _preset(monkeypatch, z0, z1, code="wfa"):
    """Make the two z-scores of one indicator exactly what a test needs, so the rule is tested apart from the tables."""
    vals, real = iter((z0, z1)), T._z
    monkeypatch.setattr(T, "_z", lambda c, *a, **k: next(vals) if c == code else real(c, *a, **k))


def _run(monkeypatch, z0, z1, hc=False):
    _preset(monkeypatch, z0, z1, "hcfa" if hc else "wfa")
    prev = PreviousVisit(200, 7.0, hc_cm=42.0 if hc else None)
    t = assess_trends("male", prev, 260, 7.5, hc_cm=43.0 if hc else None)
    return _by_name(t)["head_circumference_for_age" if hc else "weight_for_age"]


# ---- constants agree with the engine, and the z-scores agree with it ----
def test_constants_equal_the_engines():
    assert T.PLAUSIBLE["wfa"] == anthro_engine._PLAUSIBLE["wfa"] and T.PLAUSIBLE["lhfa"] == anthro_engine._PLAUSIBLE["lhfa"]
    assert T.LENGTH_MAX_AGE_DAYS == anthro_engine.LENGTH_MAX_AGE_DAYS and T.LENHEI_OFFSET_CM == anthro_engine.LENHEI_OFFSET_CM
    assert T.DAYS_PER_MONTH == anthro_engine.DAYS_PER_MONTH and T.MAX_AGE_DAYS == anthro_engine.MAX_AGE_DAYS
    assert MIN_INTERVAL_DAYS == 28 and T.TREND_SD == 1.0


def test_weight_and_length_z_scores_equal_the_anthro_engine_for_the_same_child():
    rng = random.Random(11)
    for _ in range(300):
        sex = rng.choice(("male", "female"))
        a = rng.randint(0, 1700)
        w, h = rng.uniform(3, 18), rng.uniform(50, 110)
        pos = rng.choice(("length", "height"))
        ref = compute_anthropometry(sex=sex, weight_kg=w, length_height_cm=h, measure_position=pos, age_days=a)
        assert T._z("wfa", sex, a, w, None) == pytest.approx(ref.wfa.z)
        assert T._z("lhfa", sex, a, h, pos) == pytest.approx(ref.lhfa.z)


def test_head_circumference_z_is_zero_at_the_median_and_one_at_plus_one_sd():
    from thanzi_screen.anthro import tables
    for sex in ("male", "female"):
        for r in tables._read_verified(f"hcfa_{'boys' if sex == 'male' else 'girls'}_0_13.csv")[:13]:
            days = int(r["Week"]) * 7
            assert T._z("hcfa", sex, days, float(r["SD0"]), None) == pytest.approx(0.0, abs=0.06)
            assert T._z("hcfa", sex, days, float(r["SD1"]), None) == pytest.approx(1.0, abs=0.06)
            assert T._z("hcfa", sex, days, float(r["SD2neg"]), None) == pytest.approx(-2.0, abs=0.06)


# ---- the rule, with exact z-scores ----
@pytest.mark.parametrize("z0,z1,flag", [(0.0, -1.0, True), (0.0, -0.99, False), (-0.5, -1.4, False), (1.3, 0.2, True),
                                         (-1.0, -2.4, True), (0.4, 1.9, False)])
def test_weight_is_flagged_for_a_fall_of_a_full_band_and_not_for_less_or_for_a_rise(monkeypatch, z0, z1, flag):
    t = _run(monkeypatch, z0, z1)
    assert t.assessed and t.flagged is flag
    assert (len(t.messages) > 0) is flag and t.z_change == pytest.approx(round(z1 - z0, 2))


@pytest.mark.parametrize("z0,z1,status", [(-1.9, -2.05, "below_minus2"), (-2.5, -3.01, "below_minus3"), (-1.0, -3.2, "below_minus3"),
                                           (-2.1, -2.3, None), (-3.5, -3.9, None), (-1.95, -1.99, None),
                                           (-1.9, -2.0, None), (-2.9, -3.0, None), (-2.0, -2.01, "below_minus2"), (-3.0, -3.01, "below_minus3")])
def test_a_small_fall_that_newly_passes_minus_2_or_minus_3_is_flagged_with_its_status(monkeypatch, z0, z1, status):
    t = _run(monkeypatch, z0, z1)
    assert t.status_change == status
    if status:
        assert t.flagged and t.direction == "fell" and T.MESSAGES[status] in t.messages
    else:
        assert t.flagged == (round(z1 - z0, 6) <= -1.0)


def test_a_child_already_below_minus_2_who_stays_there_is_not_flagged_for_that_alone(monkeypatch):
    t = _run(monkeypatch, -2.4, -2.5)
    assert not t.flagged and t.status_change is None and t.direction == "steady"


@pytest.mark.parametrize("z0,z1,crossed", [(0.3, -1.2, (0, -1)), (-0.5, -2.1, (-1, -2)), (1.5, 0.5, (1,)), (-0.4, 0.2, (0,)),
                                            (-1.5, 0.5, (-1, 0)), (3.4, 2.2, (3,)), (-3.4, -3.8, ())])
def test_lines_crossed_lists_the_whole_z_score_lines_between_the_values(monkeypatch, z0, z1, crossed):
    _preset(monkeypatch, z0, z1)
    t = _by_name(assess_trends("male", PreviousVisit(100, 6.0), 160, 6.5))["weight_for_age"]
    assert t.lines_crossed == crossed


def test_a_rise_in_weight_is_reported_not_flagged(monkeypatch):
    t = _run(monkeypatch, -0.5, 1.2)
    assert t.direction == "rose" and not t.flagged and t.messages == ()


@pytest.mark.parametrize("z0,z1,flag,direction", [(0.0, -1.0, True, "fell"), (0.0, 1.0, True, "rose"), (0.0, 0.99, False, "steady"),
                                                   (1.8, 2.7, False, "steady"), (-0.2, 2.1, True, "rose")])
def test_head_size_is_flagged_for_a_change_of_a_full_band_in_either_direction(monkeypatch, z0, z1, flag, direction):
    t = _run(monkeypatch, z0, z1, hc=True)
    assert t.flagged is flag and t.direction == direction and t.status_change is None
    if flag:
        assert t.messages == (T.MESSAGES["hcfa_fell" if direction == "fell" else "hcfa_rose"],)


def test_head_size_has_no_single_value_cut_off(monkeypatch):
    t = _run(monkeypatch, -2.2, -2.6, hc=True)                      # newly below -2 does not count by itself for head size
    assert not t.flagged and t.status_change is None


# ---- real data ----
def test_the_guide_case_fadi_length_falls_across_lines_and_is_flagged_but_weight_is_not():
    # WHO technical guide p. 43: boy, 4 months 62.3 cm / 6.5 kg, 18 months 75.1 cm / 12.0 kg. Stunted by length, weight normal.
    t = _by_name(assess_trends("male", PreviousVisit(122, 6.5, 62.3, "length"), 548, 12.0, 75.1, "length"))
    L, W = t["length_height_for_age"], t["weight_for_age"]
    assert L.flagged and L.direction == "fell" and L.status_change == "below_minus2" and L.z_previous > -1 > -2 > L.z_current
    assert L.lines_crossed == (-1, -2) and L.z_change <= -1.0
    assert not W.flagged and -2 < W.z_current < 2


def test_a_child_who_grows_along_the_median_has_nothing_flagged():
    t = assess_trends("female", PreviousVisit(200, 7.4, 66.0, "length", 42.0), 260, 8.0, 68.0, "length", 43.0)
    assert [i.assessed for i in t.indicators] == [True, True, True] and not t.flagged
    assert all(i.direction == "steady" and i.messages == () for i in t.indicators)


def test_a_real_head_circumference_rise_across_a_line_is_flagged():
    # a girl at 40 and 120 days: 38.0 cm is about the median at 40 days, 44.5 cm at 120 days is well above the median
    t = _by_name(assess_trends("female", PreviousVisit(40, 4.4, hc_cm=38.0), 120, 5.8, hc_cm=44.5))
    h = t["head_circumference_for_age"]
    assert h.assessed and h.flagged and h.direction == "rose" and h.z_change >= 1.0


# ---- which indicators appear ----
def test_weight_is_always_there_and_the_others_only_when_both_visits_have_them():
    only_w = assess_trends("male", PreviousVisit(200, 7.0), 260, 7.5, 68.0, "length", 43.0)
    assert [i.indicator for i in only_w.indicators] == ["weight_for_age"]
    cur_missing = assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length", 42.0), 260, 7.5)
    assert [i.indicator for i in cur_missing.indicators] == ["weight_for_age"]
    both = assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length", 42.0), 260, 7.5, 68.0, "length", 43.0)
    assert [i.indicator for i in both.indicators] == ["weight_for_age", "length_height_for_age", "head_circumference_for_age"]


def test_a_different_measure_position_at_the_two_visits_is_converted_like_the_engine():
    a = _by_name(assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length"), 260, 7.5, 67.5, "length"))
    b = _by_name(assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length"), 260, 7.5, 66.8, "height"))   # +0.7 cm -> 67.5
    assert a["length_height_for_age"].z_current == pytest.approx(b["length_height_for_age"].z_current, abs=0.011)


# ---- not assessed, with a reason ----
def test_interval_boundary_is_28_days_for_every_indicator():
    prev = PreviousVisit(200, 7.0, 66.0, "length", 42.0)
    short = assess_trends("male", prev, 227, 7.4, 67.0, "length", 42.5)
    assert all(not i.assessed and i.reason == "interval_too_short" and i.z_change is None and not i.flagged for i in short.indicators)
    assert not short.flagged and short.interval_days == 27
    ok = assess_trends("male", prev, 228, 7.4, 67.0, "length", 42.5)
    assert all(i.assessed for i in ok.indicators)


def test_oedema_switches_off_weight_only():
    t = _by_name(assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length"), 260, 9.9, 68.0, "length", oedema=True))
    assert not t["weight_for_age"].assessed and t["weight_for_age"].reason == "oedema_weight_unreliable"
    assert t["length_height_for_age"].assessed


def test_past_the_engines_last_day_nothing_is_assessed_and_past_60_months_head_size_is_not():
    t = assess_trends("male", PreviousVisit(1800, 17.0, 108.0, "height", 50.0), 1857, 17.5, 109.0, "height", 50.2)
    assert all(i.reason == "outside_reference_ages" for i in t.indicators)
    t = _by_name(assess_trends("male", PreviousVisit(1700, 17.0, 108.0, "height", 50.0), 1850, 17.5, 109.0, "height", 50.2))
    assert t["head_circumference_for_age"].reason == "outside_reference_ages"
    assert t["weight_for_age"].assessed and t["length_height_for_age"].assessed


@pytest.mark.parametrize("kw,which", [({"weight_kg": 80.0}, "weight_for_age"), ({"hc_cm": 70.0}, "head_circumference_for_age"),
                                       ({"length_height_cm": 20.0}, "length_height_for_age")])
def test_an_implausible_value_is_not_read_as_a_trend(kw, which):
    base = dict(weight_kg=7.5, length_height_cm=68.0, hc_cm=43.0)
    base.update(kw)
    t = _by_name(assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length", 42.0), 260, base["weight_kg"], base["length_height_cm"],
                               "length", base["hc_cm"]))
    assert not t[which].assessed and t[which].reason == "implausible_measurement" and not t[which].flagged and t[which].messages


def test_an_impossibly_small_length_after_conversion_is_implausible_not_an_error():
    t = _by_name(assess_trends("male", PreviousVisit(900, 12.0, 90.0, "height"), 960, 12.4, 0.5, "length"))
    assert t["length_height_for_age"].reason == "implausible_measurement"


# ---- invalid input ----
@pytest.mark.parametrize("call", [
    lambda: assess_trends("x", PreviousVisit(100, 6.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(160, 6.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(170, 6.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(-1, 6.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(100.5, 6.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(True, 6.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(100, 0.0), 160, 6.5),
    lambda: assess_trends("male", PreviousVisit(100, 6.0), 160, -6.5),
    lambda: assess_trends("male", PreviousVisit(100, 6.0), 160, float("nan")),
    lambda: assess_trends("male", PreviousVisit(100, 6.0, 60.0, None), 160, 6.5, 62.0, "length"),
    lambda: assess_trends("male", PreviousVisit(100, 6.0, 60.0, "length"), 160, 6.5, 62.0, None),
    lambda: assess_trends("male", PreviousVisit(100, 6.0, 60.0, "sitting"), 160, 6.5, 62.0, "length"),
    lambda: assess_trends("male", PreviousVisit(100, 6.0, hc_cm=-1.0), 160, 6.5, hc_cm=40.0),
    lambda: assess_trends("male", PreviousVisit(100, 6.0, hc_cm=40.0), 160, 6.5, hc_cm=0),
])
def test_invalid_input_raises_value_error(call):
    with pytest.raises(ValueError):
        call()


# ---- invariants ----
def test_invariants_over_random_inputs():
    rng = random.Random(5)
    for _ in range(2000):
        sex = rng.choice(("male", "female"))
        a = rng.randint(0, 1700)
        b = a + rng.randint(1, 160)
        prev = PreviousVisit(a, rng.uniform(3, 17), rng.choice((None, rng.uniform(50, 105))), "length" if a < 700 else "height",
                             rng.choice((None, rng.uniform(33, 51))))
        t = assess_trends(sex, prev, b, rng.uniform(3, 18), rng.choice((None, rng.uniform(50, 110))), "length" if b < 700 else "height",
                          rng.choice((None, rng.uniform(33, 52))), oedema=rng.random() < 0.1)
        assert t.interval_days == b - a and t.flagged == any(i.flagged for i in t.indicators)
        assert t.indicators[0].indicator == "weight_for_age"
        for i in t.indicators:
            assert i.assessed == (i.reason is None) and (i.flagged <= i.assessed)
            if i.assessed:
                assert i.z_change == pytest.approx(i.z_current - i.z_previous, abs=0.011)
                assert i.flagged == (bool(i.messages)) and i.direction in ("fell", "rose", "steady")
                assert i.status_change is None or i.indicator != "head_circumference_for_age"
                assert all(-3 <= k <= 3 for k in i.lines_crossed)
                if i.indicator != "head_circumference_for_age":
                    assert not (i.direction == "rose" and i.flagged)
            else:
                assert i.messages and i.z_change is None and not i.flagged


def test_the_result_cites_its_references_and_is_advisory():
    t = assess_trends("male", PreviousVisit(200, 7.0, 66.0, "length", 42.0), 260, 7.5, 68.0, "length", 43.0)
    assert {i.indicator: i.reference for i in t.indicators} == {"weight_for_age": "R5", "length_height_for_age": "R4",
                                                                 "head_circumference_for_age": "R20"}
    assert all(i.guide == "R21" for i in t.indicators) and "does not change" in t.advisory
    assert "clinician" in T.REVIEW_NOTE


# ---- stdlib only, and nothing outside the API service imports it ----
def test_trend_module_imports_only_the_standard_library_and_its_own_package():
    std = set(__import__("sys").stdlib_module_names)
    tree = ast.parse((SRC / "growth" / "trend.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.level > 0 or node.module.split(".")[0] in std
            if node.level:
                assert (node.module or "").split(".")[0] in ("anthro", "velocity", "")
        elif isinstance(node, ast.Import):
            assert all(a.name.split(".")[0] in std for a in node.names)
