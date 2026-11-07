import hashlib
import json

import pytest

from thanzi_screen.anthro import tables
from thanzi_screen.anthro.lms import sd_value, zscore_adjusted

SEXES = ("male", "female")
SD_COLS = {-3: "SD3neg", -2: "SD2neg", -1: "SD1neg", 0: "SD0", 1: "SD1", 2: "SD2", 3: "SD3"}


def _rows(indicator, sex):
    return tables._read_verified(tables._filename(indicator, sex))


def test_manifest_checksums_match_files():
    for name, meta in tables.manifest().items():
        raw = (tables._DIR / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == meta["csv_sha256"]


def test_tampered_table_is_rejected(monkeypatch):
    bad = json.loads(json.dumps(tables.manifest()))
    bad["wfa_boys.csv"]["csv_sha256"] = "0" * 64
    monkeypatch.setattr(tables, "manifest", lambda: bad)
    tables.age_table.cache_clear()
    with pytest.raises(tables.TableIntegrityError):
        tables.age_table("wfa", "male")
    tables.age_table.cache_clear()


@pytest.mark.parametrize("sex", SEXES)
@pytest.mark.parametrize("indicator", ["wfa", "lhfa"])
def test_age_tables_cover_days_0_to_1856(indicator, sex):
    assert len(tables.age_table(indicator, sex)) == 1857


@pytest.mark.parametrize("sex", SEXES)
@pytest.mark.parametrize("indicator", ["wfa", "lhfa"])
def test_age_tables_match_published_sd_columns(indicator, sex):
    # WHO publishes SD values to 3 decimals; LMS formula must reproduce -3..+3
    for r in _rows(indicator, sex):
        L, M, S = float(r["L"]), float(r["M"]), float(r["S"])
        for k, col in SD_COLS.items():
            assert sd_value(M, L, S, k) == pytest.approx(float(r[col]), abs=0.0011)


@pytest.mark.parametrize("sex", SEXES)
def test_lhfa_published_sd4_matches_plain_lms(sex):
    # Confirms length/height-for-age is NOT adjusted beyond +/-3 (WHO table itself)
    for r in _rows("lhfa", sex):
        L, M, S = float(r["L"]), float(r["M"]), float(r["S"])
        assert sd_value(M, L, S, 4) == pytest.approx(float(r["SD4"]), abs=0.0011)
        assert sd_value(M, L, S, -4) == pytest.approx(float(r["SD4neg"]), abs=0.0011)


@pytest.mark.parametrize("sex", SEXES)
def test_wfa_published_sd4_matches_adjusted_method(sex):
    # Confirms weight-for-age IS adjusted: WHO's +/-4 SD values equal the
    # linear extension of the SD2-SD3 distance, not the plain LMS value.
    for r in _rows("wfa", sex):
        L, M, S = float(r["L"]), float(r["M"]), float(r["S"])
        for k, col in ((4, "SD4"), (-4, "SD4neg")):
            y = float(r[col])
            assert zscore_adjusted(y, M, L, S) == pytest.approx(k, abs=0.01)


@pytest.mark.parametrize("sex", SEXES)
@pytest.mark.parametrize("indicator", ["wfl", "wfh"])
def test_lenhei_tables_match_published_sd_columns(indicator, sex):
    # WHO publishes these cut-offs to 1 decimal
    for r in _rows(indicator, sex):
        key = "Length" if indicator == "wfl" else "Height"
        L, M, S = float(r["L"]), float(r["M"]), float(r["S"])
        assert key in r
        for k, col in SD_COLS.items():
            assert sd_value(M, L, S, k) == pytest.approx(float(r[col]), abs=0.0501)


def test_lenhei_ranges():
    for sex in SEXES:
        assert (tables.lenhei_table("wfl", sex).min, tables.lenhei_table("wfl", sex).max) == (45, 110)
        assert (tables.lenhei_table("wfh", sex).min, tables.lenhei_table("wfh", sex).max) == (65, 120)


def test_interpolation_exact_node_and_midpoint():
    t = tables.lenhei_table("wfl", "male")
    i = t.x.index(60.0)
    assert t.lookup(60.0) == t.lms[i]
    mid = t.lookup(60.25)
    for a, b, c in zip(t.lms[i], t.lms[i + 1], mid):
        assert c == pytest.approx((a + b) / 2)


def test_interpolation_is_monotone_between_rows():
    t = tables.lenhei_table("wfh", "female")
    m = [t.lookup(70 + d / 10)[1] for d in range(0, 6)]
    assert m == sorted(m)


@pytest.mark.parametrize("x", [44.9, 110.1])
def test_wfl_outside_range_is_none(x):
    assert tables.lenhei_table("wfl", "female").lookup(x) is None


@pytest.mark.parametrize("x", [64.9, 120.1])
def test_wfh_outside_range_is_none(x):
    assert tables.lenhei_table("wfh", "male").lookup(x) is None


def test_unknown_table_key():
    with pytest.raises(KeyError):
        tables.age_table("bmi", "male")
