from datetime import date

import pytest

from thanzi_screen.anthro import InputError, compute_anthropometry, tables
from thanzi_screen.anthro.lms import sd_value
from thanzi_screen.anthro.engine import FLAG_ADJUSTED, FLAG_IMPLAUSIBLE, WARN_CONVERTED


def run(**kw):
    base = dict(sex="male", weight_kg=8.0, length_height_cm=70.0, measure_position="length", age_days=300)
    base.update(kw)
    return compute_anthropometry(**base)


def test_median_child_is_near_zero():
    L, M, S = tables.age_table("wfa", "female")[300]
    lh = tables.age_table("lhfa", "female")[300][1]
    r = run(sex="female", weight_kg=M, length_height_cm=lh)
    assert r.wfa.z == pytest.approx(0, abs=1e-9)
    assert r.lhfa.z == pytest.approx(0, abs=1e-9)


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("k", [-3, -2, -1, 1, 2, 3])
def test_weight_at_published_sd_gives_that_z(sex, k):
    L, M, S = tables.age_table("wfa", sex)[400]
    r = run(sex=sex, weight_kg=sd_value(M, L, S, k), age_days=400)
    assert r.wfa.z == pytest.approx(k, abs=1e-6)


@pytest.mark.parametrize("sex", ["male", "female"])
@pytest.mark.parametrize("length", [50.0, 67.5, 85.0, 109.5])
def test_wfl_at_sd_cutoffs_on_table_node(sex, length):
    L, M, S = tables.lenhei_table("wfl", sex).lookup(length)
    for k in (-3, -2, 0, 2):
        r = run(sex=sex, weight_kg=sd_value(M, L, S, k), length_height_cm=length, age_days=500)
        assert r.wflh.indicator == "wfl"
        assert r.wflh.z == pytest.approx(k, abs=1e-6)


def test_table_selection_at_730_731_boundary():
    assert run(age_days=730, length_height_cm=85.0).wflh.indicator == "wfl"
    assert run(age_days=731, length_height_cm=85.0, measure_position="height").wflh.indicator == "wfh"


def test_lhfa_discontinuity_uses_length_then_height_table():
    r730 = run(age_days=730, length_height_cm=87.8018)  # median of length table day 730 (boys)
    r731 = run(age_days=731, length_height_cm=87.1303, measure_position="height")
    assert r730.lhfa.z == pytest.approx(0, abs=1e-3)
    assert r731.lhfa.z == pytest.approx(0, abs=1e-3)


def test_position_conversion_young_child_standing_height_adds_0_7():
    a = run(age_days=300, length_height_cm=70.0, measure_position="height")
    b = run(age_days=300, length_height_cm=70.7, measure_position="length")
    assert a.length_height_used_cm == pytest.approx(70.7)
    assert WARN_CONVERTED in a.warnings and WARN_CONVERTED not in b.warnings
    assert a.wflh.z == pytest.approx(b.wflh.z)
    assert a.lhfa.z == pytest.approx(b.lhfa.z)


def test_position_conversion_older_child_recumbent_subtracts_0_7():
    a = run(age_days=900, length_height_cm=90.7, measure_position="length")
    b = run(age_days=900, length_height_cm=90.0, measure_position="height")
    assert a.length_height_used_cm == pytest.approx(90.0)
    assert WARN_CONVERTED in a.warnings
    assert a.wflh.z == pytest.approx(b.wflh.z)


def test_oedema_suppresses_weight_based_scores_only():
    r = run(oedema=True)
    assert r.wfa.status == r.wflh.status == "not_computable"
    assert r.wfa.reason == "oedema_weight_unreliable"
    assert r.lhfa.status == "ok"


def test_age_from_dates_and_months():
    r = run(age_days=None, date_of_birth=date(2024, 1, 1), measurement_date=date(2024, 10, 28))
    assert r.age_days == 301
    assert r.age_months == pytest.approx(301 / 30.4375)


@pytest.mark.parametrize("days,ok", [(0, True), (1856, True), (1857, False)])
def test_age_range_limits(days, ok):
    r = run(age_days=days, weight_kg=3.3 if days == 0 else 17.0, length_height_cm=50.0 if days == 0 else 100.0,
            measure_position="length" if days == 0 else "height")
    assert (r.wfa.status == "ok") is ok
    if not ok:
        assert r.wfa.reason == "age_out_of_range_0_1856_days"


@pytest.mark.parametrize("cm,ok", [(44.9, False), (45.0, True), (110.0, True), (110.1, False)])
def test_wfl_length_range_limits(cm, ok):
    r = run(age_days=700, length_height_cm=cm)
    assert (r.wflh.status == "ok") is ok


@pytest.mark.parametrize("cm,ok", [(64.9, False), (65.0, True), (120.0, True), (120.1, False)])
def test_wfh_height_range_limits(cm, ok):
    r = run(age_days=900, length_height_cm=cm, measure_position="height")
    assert (r.wflh.status == "ok") is ok


def test_adjusted_flag_and_implausible_flag():
    L, M, S = tables.lenhei_table("wfl", "male").lookup(70.0)
    sd2, sd3 = sd_value(M, L, S, -2), sd_value(M, L, S, -3)
    # about -3.5 SD: adjusted, but still plausible
    r = run(weight_kg=sd3 - 0.5 * (sd2 - sd3), length_height_cm=70.0, age_days=500)
    assert r.wflh.z == pytest.approx(-3.5, abs=1e-6)
    assert FLAG_ADJUSTED in r.wflh.flags and FLAG_IMPLAUSIBLE not in r.wflh.flags
    assert r.wflh.z_unadjusted < r.wflh.z  # plain z overshoots below -3.5
    # about -6 SD: also implausible
    r = run(weight_kg=sd3 - 3.0 * (sd2 - sd3), length_height_cm=70.0, age_days=500)
    assert r.wflh.z == pytest.approx(-6.0, abs=1e-6)
    assert FLAG_IMPLAUSIBLE in r.wflh.flags


def test_no_flags_inside_3_sd():
    r = run()
    assert r.wfa.flags == r.lhfa.flags == r.wflh.flags == ()


def test_lhfa_is_never_adjusted():
    L, M, S = tables.age_table("lhfa", "male")[300]
    r = run(length_height_cm=sd_value(M, L, S, -4), age_days=300)
    assert r.lhfa.z == pytest.approx(-4, abs=1e-6)
    assert FLAG_ADJUSTED not in r.lhfa.flags


@pytest.mark.parametrize("kw", [
    dict(sex="other"), dict(measure_position="sitting"),
    dict(weight_kg=0), dict(weight_kg=-1), dict(weight_kg=float("nan")), dict(weight_kg="8"), dict(weight_kg=True),
    dict(length_height_cm=0), dict(length_height_cm=float("inf")),
    dict(age_days=-1), dict(age_days=1.5), dict(age_days=True),
    dict(age_days=None),
    dict(date_of_birth=date(2024, 1, 1), measurement_date=date(2024, 6, 1)),  # age_days also given
    dict(age_days=None, date_of_birth=date(2024, 6, 1), measurement_date=date(2024, 1, 1)),
    dict(age_days=None, date_of_birth=date(2024, 6, 1)),
])
def test_bad_inputs_raise(kw):
    with pytest.raises(InputError):
        run(**kw)


def test_deterministic():
    assert run() == run()
