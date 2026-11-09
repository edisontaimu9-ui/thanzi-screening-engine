"""WHO head circumference-for-age tables (R20): integrity, shape, lookup and the weekly/monthly hand-over. Synthetic only."""
import hashlib
import json

import pytest

from thanzi_screen.anthro import engine, tables

SEXES = ("male", "female")
SD_COLS = {-3: "SD3neg", -2: "SD2neg", -1: "SD1neg", 0: "SD0", 1: "SD1", 2: "SD2", 3: "SD3"}


def _rows(sex, span):
    return tables._read_verified(f"hcfa_{'boys' if sex == 'male' else 'girls'}_{span}.csv")


def test_the_four_tables_are_in_the_manifest_with_checksums_and_the_register_id():
    m = tables.manifest()
    names = [f"hcfa_{s}_{span}.csv" for s in ("boys", "girls") for span in ("0_13", "0_5")]
    for n in names:
        assert m[n]["register_id"] == "R20" and m[n]["indicator"] == "hcfa"
        assert hashlib.sha256((tables._DIR / n).read_bytes()).hexdigest() == m[n]["csv_sha256"]
    assert {m[n]["data_rows"] for n in names} == {14, 61}
    assert m["hcfa_boys_0_13.csv"]["source_file"] == "hcfa-boys-0-13-zscores.xlsx"


def test_the_existing_tables_are_untouched_by_adding_head_circumference():
    m = tables.manifest()
    assert m["wfa_boys.csv"]["source_sha256"].startswith("b5b4748c") and m["lhfa_boys.csv"]["source_sha256"].startswith("c4b1c902")
    assert len([k for k in m if not k.startswith("hcfa")]) == 8


def test_a_tampered_head_table_is_rejected(monkeypatch):
    bad = json.loads(json.dumps(tables.manifest()))
    bad["hcfa_boys_0_5.csv"]["csv_sha256"] = "0" * 64
    monkeypatch.setattr(tables, "manifest", lambda: bad)
    tables.hc_table.cache_clear()
    with pytest.raises(tables.TableIntegrityError):
        tables.hc_table("male", "0_5")
    tables.hc_table.cache_clear()


@pytest.mark.parametrize("sex", SEXES)
def test_table_shape_weekly_0_to_13_and_monthly_0_to_60_with_l_equal_one(sex):
    weekly, monthly = _rows(sex, "0_13"), _rows(sex, "0_5")
    assert [int(r["Week"]) for r in weekly] == list(range(14)) and [int(r["Month"]) for r in monthly] == list(range(61))
    assert all(float(r["L"]) == 1.0 for r in weekly + monthly)
    assert float(weekly[0]["M"]) == float(monthly[0]["M"])                      # birth is the same row in both


@pytest.mark.parametrize("sex", SEXES)
@pytest.mark.parametrize("span", ["0_13", "0_5"])
def test_published_sd_columns_match_the_lms_values(sex, span):
    # WHO prints these to one decimal, so the formula must land within half of that (plus a hair).
    for r in _rows(sex, span):
        m, s = float(r["M"]), float(r["S"])
        assert float(r["SD"]) == pytest.approx(m * s, abs=0.0006)
        for k, col in SD_COLS.items():
            assert m * (1 + s * k) == pytest.approx(float(r[col]), abs=0.0501)


@pytest.mark.parametrize("sex", SEXES)
def test_lookup_returns_the_table_rows_at_the_nodes(sex):
    weekly, monthly = _rows(sex, "0_13"), _rows(sex, "0_5")
    for w in (0, 1, 7, 13):                                                     # whole weeks, in days
        r = weekly[w]
        assert tables.hc_lms(sex, w * 7) == (float(r["L"]), float(r["M"]), float(r["S"]))
    for r in monthly[4:60]:                                                     # month 60 is 1826.25 days: past the last whole day
        days = int(r["Month"]) * tables.HC_DAYS_PER_MONTH
        lo, hi = int(days), int(days) + 1
        m0, m1 = tables.hc_lms(sex, lo)[1], tables.hc_lms(sex, hi)[1]
        assert min(m0, m1) - 1e-9 <= float(r["M"]) <= max(m0, m1) + 1e-9        # the row's M lies between the two day values


@pytest.mark.parametrize("sex", SEXES)
def test_interpolation_is_linear_between_rows(sex):
    weekly = _rows(sex, "0_13")
    m3, m4 = float(weekly[3]["M"]), float(weekly[4]["M"])
    day = 24                                                                    # 3 weeks and 3 days
    assert tables.hc_lms(sex, day)[1] == pytest.approx(m3 + (3 / 7) * (m4 - m3))
    monthly = _rows(sex, "0_5")
    m12, m13 = float(monthly[12]["M"]), float(monthly[13]["M"])
    day = 380
    w = day / tables.HC_DAYS_PER_MONTH - 12
    assert tables.hc_lms(sex, day)[1] == pytest.approx(m12 + w * (m13 - m12))


def test_the_weekly_table_covers_up_to_day_91_and_the_monthly_table_takes_over_after():
    assert tables.HC_WEEKLY_MAX_DAYS == 91
    assert tables.hc_lms("male", 91) == tuple(float(x) for x in (_rows("male", "0_13")[13][k] for k in ("L", "M", "S")))
    m = tables.hc_lms("male", 92)[1]
    assert m == pytest.approx(float(_rows("male", "0_5")[3]["M"]) + (92 / tables.HC_DAYS_PER_MONTH - 3)
                              * (float(_rows("male", "0_5")[4]["M"]) - float(_rows("male", "0_5")[3]["M"])))
    assert abs(m - tables.hc_lms("male", 91)[1]) < 0.2                          # no jump at the hand-over


@pytest.mark.parametrize("sex", SEXES)
def test_there_is_no_value_past_60_months(sex):
    assert tables.hc_lms(sex, 1826) is not None and tables.hc_lms(sex, 1827) is None and tables.hc_lms(sex, 1856) is None
    assert tables.hc_lms(sex, -1) is None


def test_boys_are_larger_than_girls_at_birth_and_at_five_years():
    assert tables.hc_lms("male", 0)[1] > tables.hc_lms("female", 0)[1]
    assert tables.hc_lms("male", 1800)[1] > tables.hc_lms("female", 1800)[1]


def test_bad_arguments_are_rejected():
    with pytest.raises(KeyError):
        tables.hc_table("other", "0_5")
    with pytest.raises(KeyError):
        tables.hc_table("male", "0_99")


def test_the_day_constant_equals_the_engines():
    assert tables.HC_DAYS_PER_MONTH == engine.DAYS_PER_MONTH
