"""DHIS2 export: data value set shape, mapping checks (fail closed), small counts, one level only."""
import pytest

from thanzi_screen.surveillance import Dhis2Mapping, FacilityRow, OrgUnit, SurveillanceInputError, build_data_value_set, mapping_template
from thanzi_screen.surveillance.dhis2 import ELEMENTS

P = "2026-10"
UNITS = [OrgUnit("MW", "Malawi", "national"), OrgUnit("MW-ZA", "Zomba", "district", "MW"),
         OrgUnit("MW-ZA-F1", "Zomba Central Hospital", "facility", "MW-ZA"), OrgUnit("MW-ZA-F2", "Matawale Health Centre", "facility", "MW-ZA"),
         OrgUnit("MW-ZA-F3", "Chilipa Clinic", "facility", "MW-ZA")]
ROWS = [FacilityRow("MW-ZA-F1", P, 200, 12, 20, 3), FacilityRow("MW-ZA-F2", P, 90, 0, 8, 0)]
MAP = Dhis2Mapping(elements={"screened": "THZ_SCREENED", "sam": "THZ_SAM", "mam": "THZ_MAM", "unable": "THZ_UNABLE"})


def values(out):
    return {(v["orgUnit"], v["dataElement"]): v["value"] for v in out["data_value_set"]["dataValues"]}


def test_shape_period_and_values_are_strings():
    out = build_data_value_set(UNITS, ROWS, MAP)
    dvs = out["data_value_set"]
    assert dvs["period"] == "202610" and "dataSet" not in dvs
    assert all(set(v) == {"dataElement", "orgUnit", "value"} and isinstance(v["value"], str) for v in dvs["dataValues"])
    v = values(out)
    assert v[("MW-ZA-F1", "THZ_SAM")] == "12" and v[("MW-ZA-F1", "THZ_SCREENED")] == "200" and v[("MW-ZA-F1", "THZ_UNABLE")] == "3"
    assert out["import_parameters"] == {"dataElementIdScheme": "CODE", "orgUnitIdScheme": "CODE", "importStrategy": "CREATE_AND_UPDATE",
                                        "dryRun": "true"}


def test_facilities_only_never_district_or_national_totals():
    out = build_data_value_set(UNITS, ROWS, MAP)
    assert {o for o, _ in values(out)} == {"MW-ZA-F1", "MW-ZA-F2"}


def test_zero_is_exported_and_a_non_reporting_facility_is_absent():
    out = build_data_value_set(UNITS, ROWS, MAP)
    v = values(out)
    assert v[("MW-ZA-F2", "THZ_SAM")] == "0" and not any(o == "MW-ZA-F3" for o, _ in v)
    assert out["summary"]["facilities_exported"] == 2 and out["summary"]["facilities_not_reported"] == 1


def test_small_counts_are_withheld_by_default_but_screened_stays():
    rows = [FacilityRow("MW-ZA-F1", P, 200, 3, 20, 3)]
    out = build_data_value_set(UNITS, rows, MAP)
    v = values(out)
    assert ("MW-ZA-F1", "THZ_SAM") not in v and ("MW-ZA-F1", "THZ_MAM") not in v
    assert v[("MW-ZA-F1", "THZ_SCREENED")] == "200"
    assert out["summary"]["facilities_with_withheld_counts"] == 1 and out["summary"]["small_counts_withheld"] is True


def test_unable_is_optional_and_data_set_is_included_when_given():
    m = Dhis2Mapping(elements={"screened": "A", "sam": "B", "mam": "C"}, data_set="THZ_U5")
    out = build_data_value_set(UNITS, ROWS, m)
    assert out["data_value_set"]["dataSet"] == "THZ_U5" and not any(v["dataElement"] == "THZ_UNABLE" for v in out["data_value_set"]["dataValues"])
    assert len(out["data_value_set"]["dataValues"]) == 6


def test_uid_scheme_needs_a_mapping_for_every_facility_and_uses_it():
    uid = Dhis2Mapping(elements={"screened": "aBcDeFgHiJk", "sam": "bBcDeFgHiJk", "mam": "cBcDeFgHiJk"}, data_element_id_scheme="UID",
                       org_unit_id_scheme="UID", org_units={"MW-ZA-F1": "oBcDeFgHiJk"})
    with pytest.raises(SurveillanceInputError) as e:
        build_data_value_set(UNITS, ROWS, uid)
    assert e.value.code == "mapping_incomplete"
    full = Dhis2Mapping(**{**uid.__dict__, "org_units": {"MW-ZA-F1": "oBcDeFgHiJk", "MW-ZA-F2": "pBcDeFgHiJk"}})
    out = build_data_value_set(UNITS, ROWS, full)
    assert {o for o, _ in values(out)} == {"oBcDeFgHiJk", "pBcDeFgHiJk"} and out["import_parameters"]["orgUnitIdScheme"] == "UID"


def test_code_scheme_override_replaces_the_engine_code():
    m = Dhis2Mapping(elements=MAP.elements, org_units={"MW-ZA-F1": "ZOMBA_CH"})
    assert ("ZOMBA_CH", "THZ_SAM") in values(build_data_value_set(UNITS, ROWS, m))


@pytest.mark.parametrize("m,code", [
    (Dhis2Mapping(elements={"screened": "A", "sam": "B"}), "mapping_incomplete"),
    (Dhis2Mapping(elements={}), "mapping_incomplete"),
    (Dhis2Mapping(elements={"screened": "A", "sam": "B", "mam": "C", "gam": "D"}), "invalid_mapping"),
    (Dhis2Mapping(elements={"screened": "A", "sam": "A", "mam": "C"}), "invalid_mapping"),
    (Dhis2Mapping(elements={"screened": "A", "sam": "B", "mam": "bad id!"}), "invalid_mapping"),
    (Dhis2Mapping(elements={"screened": "A", "sam": "B", "mam": "C"}, data_element_id_scheme="UID"), "invalid_mapping"),
    (Dhis2Mapping(elements={"screened": "A", "sam": "B", "mam": "C"}, data_element_id_scheme="NAME"), "invalid_mapping"),
    (Dhis2Mapping(elements={"screened": "A", "sam": "B", "mam": "C"}, org_units={"MW-ZA-F1": "X", "MW-ZA-F2": "X"}), "invalid_mapping"),
])
def test_bad_mappings_fail_closed(m, code):
    with pytest.raises(SurveillanceInputError) as e:
        build_data_value_set(UNITS, ROWS, m)
    assert e.value.code == code and "bad id!" not in e.value.message


def test_data_errors_are_the_same_as_the_report():
    with pytest.raises(SurveillanceInputError) as e:
        build_data_value_set(UNITS, [FacilityRow("MW-ZA-F1", P, 10, 9, 9)], MAP)
    assert e.value.code == "inconsistent_counts"


def test_template_lists_every_element_and_is_not_a_valid_mapping():
    t = mapping_template()
    assert set(t["elements"]) == set(ELEMENTS) and t["_elements_guide"]["sam"]["value_type"] == "INTEGER_ZERO_OR_POSITIVE"
    with pytest.raises(SurveillanceInputError):
        build_data_value_set(UNITS, ROWS, Dhis2Mapping(elements=t["elements"]))
