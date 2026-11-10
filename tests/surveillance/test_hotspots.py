"""Hotspot surveillance: statistics, small-n and suppression handling, input checks, privacy of the contract."""
import pytest

from thanzi_screen.surveillance import Row, SurveillanceInputError, assess, wilson

P = "2026-10"


def area(result, name):
    return next(a for a in result["areas"] if a["district"] == name)


def test_wilson_basics():
    lo, hi = wilson(10, 100, 1.96)
    assert 0.05 < lo < 0.10 < hi < 0.18
    assert wilson(0, 50, 1.96)[0] == 0.0 and wilson(50, 50, 1.96)[1] == 1.0
    with pytest.raises(ValueError):
        wilson(0, 0, 1.96)


def test_clear_hotspot_and_normal_district():
    r = assess([Row("Mangochi", P, 300, 15, 35), Row("Zomba", P, 300, 5, 10), Row("Dedza", P, 300, 5, 12)])
    assert area(r, "Mangochi")["status"] == "hotspot"
    assert area(r, "Zomba")["status"] in ("not_flagged", "watch")
    assert r["areas"][0]["district"] == "Mangochi"            # hotspots sort first
    assert r["period"] == P and r["summary"]["hotspot"] == 1


def test_small_n_is_insufficient_not_low_risk():
    a = area(assess([Row("Likoma", P, 29, 5, 5), Row("Zomba", P, 300, 10, 10)]), "Likoma")
    assert a["status"] == "insufficient_data" and a["prevalence"] is None and a["sam"] is None


def test_missing_latest_period_is_no_data():
    r = assess([Row("Zomba", "2026-09", 300, 10, 10), Row("Dedza", P, 300, 10, 10)])
    assert area(r, "Zomba")["status"] == "no_data"


def test_small_cells_are_suppressed_but_status_kept():
    r = assess([Row("Salima", P, 150, 2, 40), Row("Zomba", P, 300, 5, 10), Row("Dedza", P, 300, 5, 10)])
    a = area(r, "Salima")
    assert a["counts_suppressed"] and a["sam"] is None and a["mam"] is None and a["gam_cases"] is None
    assert a["prevalence"] is None and a["ci_low"] is None
    assert a["status"] == "hotspot"                           # a real hotspot is not hidden


def test_zero_cell_is_not_suppressed():
    a = area(assess([Row("Zomba", P, 300, 0, 20), Row("Dedza", P, 300, 5, 10)]), "Zomba")
    assert not a["counts_suppressed"] and a["sam"] == 0


def test_rising_trend_gives_at_least_watch():
    r = assess([Row("Zomba", "2026-09", 400, 5, 10), Row("Zomba", P, 400, 10, 25),
                Row("Dedza", "2026-09", 400, 10, 20), Row("Dedza", P, 400, 10, 20)])
    a = area(r, "Zomba")
    assert a["trend"] == "rising" and a["status"] in ("watch", "hotspot")
    assert area(r, "Dedza")["trend"] == "steady"


def test_supplied_reference_rate_used():
    r = assess([Row("Zomba", P, 300, 15, 25)], reference_rate=0.05)
    a = area(r, "Zomba")
    assert a["reference_kind"] == "supplied" and a["reference_rate"] == 0.05 and a["status"] == "hotspot"


def test_single_district_has_no_leave_one_out_reference():
    a = area(assess([Row("Zomba", P, 300, 15, 25)]), "Zomba")
    assert a["reference_rate"] is None and "no_reference_available" in a["reasons"] and a["status"] != "hotspot"


def test_high_unable_share_sets_data_quality_flag():
    a = area(assess([Row("Zomba", P, 100, 5, 5, unable=30), Row("Dedza", P, 300, 5, 10)]), "Zomba")
    assert a["data_quality_review"] is True


@pytest.mark.parametrize("rows, ref, code", [
    ([], None, "no_rows"),
    ([Row("Zomba", "2026-13", 50, 1, 1)], None, "invalid_period"),
    ([Row("Zomba", "Oct 2026", 50, 1, 1)], None, "invalid_period"),
    ([Row("Zomba", P, 50, 30, 30)], None, "inconsistent_counts"),
    ([Row("Zomba", P, -1, 0, 0)], None, "invalid_count"),
    ([Row("12.3,45.6", P, 50, 1, 1)], None, "invalid_district"),
    ([Row("Zomba", P, 50, 1, 1), Row("zomba", P, 50, 1, 1)], None, "duplicate_row"),
    ([Row("Zomba", P, 50, 1, 1)], 1.5, "invalid_reference_rate"),
])
def test_input_errors_have_stable_codes(rows, ref, code):
    with pytest.raises(SurveillanceInputError) as e:
        assess(rows, ref)
    assert e.value.code == code


def test_error_messages_never_echo_values():
    with pytest.raises(SurveillanceInputError) as e:
        assess([Row("SecretName123", P, 50, 1, 1)])
    assert "SecretName123" not in e.value.message


def test_assess_does_not_mutate_input():
    rows = [Row("Zomba", P, 300, 15, 25), Row("Dedza", P, 300, 5, 10)]
    before = list(rows)
    assess(rows)
    assert rows == before
