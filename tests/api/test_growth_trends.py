"""Growth trends in the API (D165-D171): optional length and head fields on the earlier visit, advisory, strict input."""
import json

import pytest

from tests.api._support import LOW_BASE, need_api
from thanzi_screen.api import service
from thanzi_screen.api.service import ApiError
from thanzi_screen.ml import load_models
from thanzi_screen.ml.dl import load_deep_models

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"
HG = {"X-Gateway-Key": GW}
# A boy of 18 months (WHO guide case study 2, visit 5) and his visit at 4 months. Stunted by length, weight normal.
NOW = {**LOW_BASE, "age_days": 548, "weight_kg": 12.0, "length_height_cm": 75.1, "measure_position": "length"}
FADI = {"age_days": 122, "weight_kg": 6.5, "length_height_cm": 62.3, "measure_position": "length"}
# A healthy boy of 10 months who grows along his line.
OK_NOW = {**LOW_BASE, "age_days": 305, "weight_kg": 8.55, "length_height_cm": 72.0, "measure_position": "length"}
OK_PREV = {"age_days": 274, "weight_kg": 8.3, "length_height_cm": 70.9, "measure_position": "length"}


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def deep():
    return load_deep_models()


def _g(body, models, deep, view="worker"):
    return service.screen(body, view, models, deep)["growth_monitoring"]


def test_the_guide_case_is_flagged_for_length_with_a_clinician_review_and_nothing_else_changes(models, deep):
    out = service.screen({**NOW, "previous_measurement": FADI}, "worker", models, deep)
    g = out["growth_monitoring"]
    L = g["trends"]["length_height_for_age"]
    assert L["assessed"] and L["flagged"] and L["direction"] == "fell" and L["status_change"] == "below_minus2"
    assert L["lines_crossed"] == [-1, -2] and L["reference"] == "R4" and L["guide"] == "R21"
    assert "stunting" in L["messages"][0] and "does not change" in g["advisory"]
    assert g["review_suggested"] is True and g["review_note"] == "A clinician should review this child's growth."
    assert not g["trends"]["weight_for_age"]["flagged"]
    assert "head_circumference_for_age" not in g["trends"]
    ref = service.screen(NOW, "worker", models, deep)
    out.pop("growth_monitoring")
    assert json.loads(json.dumps(out)) == json.loads(json.dumps(ref))                  # D9: the rest is identical


def test_a_child_growing_along_the_line_has_no_flag_and_no_review(models, deep):
    g = _g({**OK_NOW, "previous_measurement": OK_PREV}, models, deep)
    assert g["review_suggested"] is False and g["review_note"] is None and not g["flagged"]
    assert all(not t["flagged"] and t["messages"] == [] for t in g["trends"].values())
    assert set(g["trends"]) == {"weight_for_age", "length_height_for_age"}


def test_earlier_visit_with_only_age_and_weight_gets_the_weight_trend_and_nothing_else(models, deep):
    g = _g({**OK_NOW, "previous_measurement": {"age_days": 274, "weight_kg": 8.3}}, models, deep)
    assert set(g["trends"]) == {"weight_for_age"} and g["trends"]["weight_for_age"]["assessed"]
    assert g["reference_derived"] is False


def test_head_circumference_trend_runs_and_hc_cm_is_not_reported_as_ignored(models, deep):
    body = {**OK_NOW, "hc_cm": 46.5}
    out = service.screen({**body, "previous_measurement": {**OK_PREV, "hc_cm": 45.8}}, "worker", models, deep)
    h = out["growth_monitoring"]["trends"]["head_circumference_for_age"]
    assert h["assessed"] and h["reference"] == "R20" and not any("ignored" in w for w in out["warnings"])
    # without an earlier head measurement the field is ignored with the warning, as before
    out = service.screen({**body, "previous_measurement": OK_PREV}, "worker", models, deep)
    assert "head_circumference_for_age" not in out["growth_monitoring"]["trends"]
    assert any("ignored" in w for w in out["warnings"])


def test_a_head_circumference_jump_is_flagged_both_ways(models, deep):
    up = _g({**OK_NOW, "hc_cm": 49.5, "previous_measurement": {**OK_PREV, "hc_cm": 45.5}}, models, deep)
    down = _g({**OK_NOW, "hc_cm": 43.0, "previous_measurement": {**OK_PREV, "hc_cm": 46.0}}, models, deep)
    assert up["trends"]["head_circumference_for_age"]["direction"] == "rose" and up["review_suggested"]
    assert down["trends"]["head_circumference_for_age"]["direction"] == "fell" and down["review_suggested"]


def test_a_flagged_weight_gain_alone_also_suggests_review(models, deep):
    g = _g({**OK_NOW, "previous_measurement": {"age_days": 274, "weight_kg": 8.5}}, models, deep)
    assert g["flagged"] and g["review_suggested"] and g["review_note"]


def test_oedema_switches_off_the_weight_trend_only(models, deep):
    g = _g({**OK_NOW, "oedema": "+", "previous_measurement": OK_PREV}, models, deep)
    w = g["trends"]["weight_for_age"]
    assert not w["assessed"] and w["reason"] == "oedema_weight_unreliable" and g["trends"]["length_height_for_age"]["assessed"]


def test_short_interval_is_not_assessed_for_trends_either(models, deep):
    g = _g({**OK_NOW, "previous_measurement": {**OK_PREV, "age_days": 290}}, models, deep)
    assert all(t["reason"] == "interval_too_short" and not t["flagged"] for t in g["trends"].values()) and not g["review_suggested"]


def test_girls_three_to_six_months_say_the_range_was_derived(models, deep):
    girl = {**OK_NOW, "sex": "female", "age_days": 140, "weight_kg": 5.6, "length_height_cm": 60.0}
    g = _g({**girl, "previous_measurement": {"age_days": 100, "weight_kg": 5.5}}, models, deep)
    assert g["reference_derived"] is True and g["status"] == "below_range" and "derived" in g["messages"][-1]


@pytest.mark.parametrize("view", ["worker", "audit"])
@pytest.mark.parametrize("previous", [FADI, {**FADI, "hc_cm": 40.0}, {"age_days": 300, "weight_kg": 8.5}, OK_PREV])
@pytest.mark.parametrize("body", [NOW, {**NOW, "muac_cm": 11.0}, {**NOW, "oedema": "++"}, {**NOW, "hc_cm": 47.0}])
def test_the_rest_of_the_response_never_depends_on_growth(models, deep, body, view, previous):
    with_g = json.loads(json.dumps(service.screen({**body, "previous_measurement": previous}, view, models, deep)))
    without = json.loads(json.dumps(service.screen(body, view, models, deep)))
    with_g.pop("growth_monitoring", None)
    with_g["warnings"] = [w for w in with_g["warnings"] if "ignored" not in w]
    without["warnings"] = [w for w in without["warnings"] if "ignored" not in w]
    assert with_g == without


def test_worker_and_audit_carry_the_same_growth_result(models, deep):
    body = {**NOW, "previous_measurement": FADI}
    assert _g(body, models, deep, "worker") == _g(body, models, deep, "audit")


def test_it_works_in_degraded_mode():
    out = service.screen({**NOW, "previous_measurement": FADI}, "worker", None)
    assert out["growth_monitoring"]["review_suggested"] is True


@pytest.mark.parametrize("bad,code", [
    ({**FADI, "measure_position": None}, "missing_field"),
    ({"age_days": 122, "weight_kg": 6.5, "length_height_cm": 62.3}, "missing_field"),
    ({**FADI, "measure_position": "sitting"}, "invalid_request"),
    ({**FADI, "length_height_cm": "62.3"}, "invalid_request"),
    ({**FADI, "hc_cm": "x"}, "invalid_request"),
    ({**FADI, "hc_cm": True}, "invalid_request"),
    ({**FADI, "hc_cm": -41.0}, "invalid_input"),
    ({**FADI, "length_height_cm": 0}, "invalid_input"),
    ({**FADI, "head": 40.0}, "unknown_field"),
    ({**FADI, "name": "x"}, "unknown_field"),
])
def test_bad_earlier_visits_are_rejected_without_echoing_values(models, deep, bad, code):
    with pytest.raises(ApiError) as e:
        service.screen({**NOW, "previous_measurement": bad}, "worker", models, deep)
    assert e.value.status == 422 and e.value.code == code
    for leaked in ("62.3", "6.5", "122", "sitting", "41.0"):
        assert leaked not in e.value.message


def test_a_bad_current_head_value_is_rejected_by_the_existing_check_not_echoed(models, deep):
    with pytest.raises(ApiError) as e:
        service.screen({**NOW, "hc_cm": "forty", "previous_measurement": {**FADI, "hc_cm": 40.0}}, "worker", models, deep)
    assert e.value.status == 422 and "forty" not in e.value.message


def test_preterm_and_corrected_age_routes_still_skip_it_with_a_warning(models, deep):
    pre = {**OK_NOW, "age_days": 20, "weight_kg": 2.2, "length_height_cm": 46.0, "gestational_age_weeks": 33, "birth_weight_g": 1900,
           "previous_measurement": {"age_days": 2, "weight_kg": 1.9, "length_height_cm": 44.0, "measure_position": "length", "hc_cm": 31.0}}
    out = service.screen(pre, "worker", models, deep)
    assert out["route"] == "preterm" and "growth_monitoring" not in out and any("Growth monitoring was not run" in w for w in out["warnings"])
    cor = {**OK_NOW, "age_days": 400, "weight_kg": 6.0, "length_height_cm": 63.0, "gestational_age_weeks": 33, "birth_weight_g": 1800,
           "previous_measurement": {"age_days": 360, "weight_kg": 5.6, "length_height_cm": 61.0, "measure_position": "length"}}
    out = service.screen(cor, "worker", models, deep)
    assert out["route"] == "under5_corrected_age" and "growth_monitoring" not in out and any("Growth monitoring was not run" in w for w in out["warnings"])


def test_a_preterm_request_with_hc_cm_and_no_earlier_visit_is_unchanged(models, deep):
    pre = {**OK_NOW, "age_days": 20, "weight_kg": 2.2, "length_height_cm": 46.0, "gestational_age_weeks": 33, "birth_weight_g": 1900, "hc_cm": 31.0}
    assert "growth_monitoring" not in service.screen(pre, "worker", models, deep)


def _client(models, deep):
    return TestClient(create_app(models=models, deep_models=deep, gateway_key=GW, audit_key=AU), raise_server_exceptions=False)


def test_http_round_trip_and_the_new_fields_are_typed(models, deep):
    c = _client(models, deep)
    r = c.post("/v1/screen", json={**NOW, "hc_cm": 47.0, "previous_measurement": {**FADI, "hc_cm": 40.0}}, headers=HG)
    assert r.status_code == 200
    g = r.json()["growth_monitoring"]
    assert g["review_suggested"] is True and set(g["trends"]) == {"weight_for_age", "length_height_for_age", "head_circumference_for_age"}
    assert g["trends"]["length_height_for_age"]["lines_crossed"] == [-1, -2]


@pytest.mark.parametrize("bad", [{**FADI, "measure_position": None}, {**FADI, "measure_position": "sitting"}, {**FADI, "hc_cm": "x"},
                                 {**FADI, "length_height_cm": None, "measure_position": "length", "extra": 1}])
def test_http_rejects_bad_earlier_visits_with_422(models, deep, bad):
    r = _client(models, deep).post("/v1/screen", json={**NOW, "previous_measurement": bad}, headers=HG)
    assert r.status_code == 422 and "62.3" not in r.text


def test_openapi_documents_the_trend_fields():
    from pathlib import Path
    spec = json.loads((Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json").read_text())
    sch = spec["components"]["schemas"]
    assert {"length_height_cm", "measure_position", "hc_cm"} <= set(sch["PreviousMeasurement"]["properties"])
    assert {"trends", "review_suggested", "review_note", "reference_derived"} <= set(sch["GrowthMonitoring"]["properties"])
    assert "IndicatorTrendOut" in sch and "GrowthTrendsOut" in sch
