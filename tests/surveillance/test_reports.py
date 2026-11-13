"""Aggregated surveillance report: sums, completeness, district status, suppression (primary and secondary), input checks."""
import pytest

from thanzi_screen.surveillance import FacilityRow, OrgUnit, SurveillanceInputError, build_report

P = "2026-10"


def hierarchy(*districts):
    """districts: (code, name, [facility codes]). Facility names are derived."""
    units = [OrgUnit("MW", "Malawi", "national")]
    for dcode, dname, facs in districts:
        units.append(OrgUnit(dcode, dname, "district", "MW"))
        units += [OrgUnit(f, f"Facility {f}", "facility", dcode) for f in facs]
    return units


def unit(report, code):
    return next(u for u in [report["national"], *report["districts"], *report["facilities"]] if u["org_unit"] == code)


BASE = hierarchy(("D1", "Zomba", ["F1", "F2"]), ("D2", "Mangochi", ["F3", "F4"]))


def test_levels_are_sums_of_facilities_and_agree():
    rows = [FacilityRow("F1", P, 200, 10, 20, 2), FacilityRow("F2", P, 100, 6, 14, 1), FacilityRow("F3", P, 300, 15, 35, 4),
            FacilityRow("F4", P, 100, 5, 10, 0)]
    r = build_report(BASE, rows)
    assert unit(r, "D1")["screened"] == 300 and unit(r, "D1")["sam"] == 16 and unit(r, "D1")["mam"] == 34
    assert unit(r, "D1")["gam_cases"] == 50 and unit(r, "D1")["unable"] == 3
    n = unit(r, "MW")
    assert n["screened"] == 700 and n["sam"] == 36 and n["mam"] == 79 and n["gam_cases"] == 115
    assert n["screened"] == unit(r, "D1")["screened"] + unit(r, "D2")["screened"]
    assert n["prevalence"] == round(115 / 700, 4) and n["ci_low"] < n["prevalence"] < n["ci_high"]
    assert r["period"] == P and r["summary"]["reporting_rate"] == 1.0


def test_non_reporting_facility_is_not_reported_and_lowers_the_reporting_rate():
    r = build_report(BASE, [FacilityRow("F1", P, 200, 10, 20), FacilityRow("F3", P, 300, 15, 35)])
    f2 = unit(r, "F2")
    assert f2["data_status"] == "not_reported" and f2["screened"] is None and f2["sam"] is None     # not zero
    assert unit(r, "D1")["facilities_expected"] == 2 and unit(r, "D1")["facilities_reported"] == 1
    assert unit(r, "D1")["reporting_rate"] == 0.5
    assert r["summary"]["facilities_expected"] == 4 and r["summary"]["facilities_reported"] == 2


def test_district_with_no_report_is_no_data():
    r = build_report(BASE, [FacilityRow("F1", P, 200, 10, 20), FacilityRow("F2", P, 100, 6, 14)])
    d2 = unit(r, "D2")
    assert d2["data_status"] == "not_reported" and d2["hotspot_status"] == "no_data" and d2["screened"] is None
    assert "no_facility_reported" in d2["reasons"]


def test_hotspot_status_is_the_hotspot_rule():
    units = hierarchy(("D1", "Mangochi", ["F1"]), ("D2", "Zomba", ["F2"]), ("D3", "Dedza", ["F3"]))
    rows = [FacilityRow("F1", P, 300, 15, 35), FacilityRow("F2", P, 300, 5, 10), FacilityRow("F3", P, 300, 5, 12)]
    r = build_report(units, rows)
    assert unit(r, "D1")["hotspot_status"] == "hotspot" and r["districts"][0]["org_unit"] == "D1"      # hotspots sort first
    assert r["summary"]["districts"]["hotspot"] == 1
    assert unit(r, "D1")["reference_kind"] == "batch_leave_one_out"
    r2 = build_report(units, rows, reference_rate=0.5)
    assert unit(r2, "D1")["hotspot_status"] != "hotspot" and unit(r2, "D1")["reference_kind"] == "supplied"


def test_trend_uses_earlier_months_and_later_months_are_ignored():
    units = hierarchy(("D1", "Zomba", ["F1"]), ("D2", "Dedza", ["F2"]))
    rows = [FacilityRow("F1", "2026-09", 300, 5, 10), FacilityRow("F1", P, 300, 20, 40), FacilityRow("F1", "2026-11", 300, 1, 1),
            FacilityRow("F2", P, 300, 5, 10)]
    r = build_report(units, rows, period=P)
    assert r["period"] == P and unit(r, "D1")["trend"] == "rising" and unit(r, "D1")["screened"] == 300


def test_period_defaults_to_latest_and_must_exist():
    rows = [FacilityRow("F1", "2026-09", 100, 5, 5), FacilityRow("F1", P, 100, 5, 5)]
    assert build_report(BASE, rows)["period"] == P
    with pytest.raises(SurveillanceInputError) as e:
        build_report(BASE, rows, period="2026-08")
    assert e.value.code == "no_rows_for_period"


def test_small_facility_is_insufficient_rate_not_shown_never_low_risk():
    r = build_report(BASE, [FacilityRow("F1", P, 20, 6, 6), FacilityRow("F3", P, 300, 15, 35)])
    f1 = unit(r, "F1")
    assert f1["data_status"] == "insufficient_data" and f1["prevalence"] is None and f1["ci_low"] is None
    assert f1["gam_cases"] == 12 and "fewer_than_min_screened" in f1["reasons"]


def test_unable_share_flags_data_quality():
    r = build_report(BASE, [FacilityRow("F1", P, 100, 5, 5, 30), FacilityRow("F3", P, 300, 15, 35)])
    assert unit(r, "F1")["data_quality_review"] is True and unit(r, "F3")["data_quality_review"] is False


def test_zero_counts_are_shown_not_suppressed():
    r = build_report(BASE, [FacilityRow("F1", P, 100, 0, 20), FacilityRow("F3", P, 300, 15, 35)])
    assert unit(r, "F1")["sam"] == 0 and not unit(r, "F1")["counts_suppressed"]


def test_small_cell_is_suppressed_and_the_sibling_too_so_it_cannot_be_subtracted():
    r = build_report(BASE, [FacilityRow("F1", P, 200, 3, 10), FacilityRow("F2", P, 150, 6, 12), FacilityRow("F3", P, 300, 15, 35)])
    f1, f2, d1 = unit(r, "F1"), unit(r, "F2"), unit(r, "D1")
    assert f1["counts_suppressed"] and "small_cell_suppressed" in f1["reasons"] and f1["sam"] is None and f1["prevalence"] is None
    assert f2["counts_suppressed"] and "secondary_suppression" in f2["reasons"] and f2["sam"] is None
    assert d1["sam"] == 9 and d1["mam"] == 22 and not d1["counts_suppressed"]       # the total is shown, no child can be derived
    assert f1["screened"] == 200 and f2["screened"] == 150                            # denominators stay


def test_no_single_hidden_cell_can_be_recovered_in_any_group():
    rows = [FacilityRow("F1", P, 200, 3, 10), FacilityRow("F2", P, 150, 6, 12), FacilityRow("F3", P, 300, 2, 35),
            FacilityRow("F4", P, 100, 5, 10)]
    r = build_report(BASE, rows)
    for parent in [r["national"], *r["districts"]]:
        kids = [u for u in [*r["districts"], *r["facilities"]] if u["parent"] == parent["org_unit"]]
        hidden = [k for k in kids if k["data_status"] != "not_reported" and k["counts_suppressed"]]
        if parent["sam"] is not None:
            assert len(hidden) != 1, parent["org_unit"]                              # one hidden child under a shown total is the leak


def test_parent_is_hidden_when_no_sibling_can_cover():
    units = hierarchy(("D1", "Zomba", ["F1", "F2"]), ("D2", "Dedza", ["F3"]))
    r = build_report(units, [FacilityRow("F1", P, 200, 3, 10), FacilityRow("F2", P, 100, 0, 0), FacilityRow("F3", P, 300, 15, 35)])
    assert unit(r, "F1")["counts_suppressed"] and unit(r, "D1")["counts_suppressed"]      # D1 would equal F1
    assert not unit(r, "F2")["counts_suppressed"]


def test_hotspot_status_survives_suppression():
    units = hierarchy(("D1", "Salima", ["F1"]), ("D2", "Zomba", ["F2"]), ("D3", "Dedza", ["F3"]))
    r = build_report(units, [FacilityRow("F1", P, 150, 2, 40), FacilityRow("F2", P, 300, 5, 10), FacilityRow("F3", P, 300, 5, 10)])
    d1 = unit(r, "D1")
    assert d1["counts_suppressed"] and d1["gam_cases"] is None and d1["hotspot_status"] == "hotspot"


@pytest.mark.parametrize("bad,code", [
    (lambda u, r: ([], r), "no_org_units"),
    (lambda u, r: (u, []), "no_rows"),
    (lambda u, r: (u + [OrgUnit("F1", "Again", "facility", "D1")], r), "duplicate_org_unit"),
    (lambda u, r: (u + [OrgUnit("f1", "Again", "facility", "D1")], r), "duplicate_org_unit"),
    (lambda u, r: (u + [OrgUnit("MW2", "Other", "national")], r), "invalid_hierarchy"),
    (lambda u, r: (u + [OrgUnit("F9", "Orphan", "facility", "NOPE")], r), "invalid_hierarchy"),
    (lambda u, r: (u + [OrgUnit("F9", "Wrong parent", "facility", "MW")], r), "invalid_hierarchy"),
    (lambda u, r: (u + [OrgUnit("D9", "Zomba", "district", "MW")], r), "duplicate_district_name"),
    (lambda u, r: (u + [OrgUnit("bad code!", "X", "facility", "D1")], r), "invalid_org_unit_code"),
    (lambda u, r: (u + [OrgUnit("F9", "Clinic<script>", "facility", "D1")], r), "invalid_org_unit_name"),
    (lambda u, r: (u, [FacilityRow("NOPE", P, 10, 1, 1)]), "unknown_org_unit"),
    (lambda u, r: (u, [FacilityRow("D1", P, 10, 1, 1)]), "not_a_facility"),
    (lambda u, r: (u, [FacilityRow("F1", "2026-13", 10, 1, 1)]), "invalid_period"),
    (lambda u, r: (u, [FacilityRow("F1", P, 10, 6, 6)]), "inconsistent_counts"),
    (lambda u, r: (u, [FacilityRow("F1", P, 10, -1, 1)]), "invalid_count"),
    (lambda u, r: (u, [FacilityRow("F1", P, 10, 1, 1), FacilityRow("F1", P, 10, 1, 1)]), "duplicate_row"),
])
def test_input_errors_have_stable_codes_and_never_echo_values(bad, code):
    units, rows = bad(list(BASE), [FacilityRow("F1", P, 100, 5, 5)])
    with pytest.raises(SurveillanceInputError) as e:
        build_report(units, rows)
    assert e.value.code == code
    for leaked in ("bad code!", "Clinic<script>", "NOPE", "2026-13"):
        assert leaked not in e.value.message


def test_result_holds_no_child_level_field_and_is_deterministic():
    rows = [FacilityRow("F1", P, 200, 10, 20), FacilityRow("F3", P, 300, 15, 35)]
    a, b = build_report(BASE, rows), build_report(BASE, rows)
    assert a == b
    keys = set(a["national"])
    assert not keys & {"child_id", "name_of_child", "date_of_birth", "latitude", "longitude"}
