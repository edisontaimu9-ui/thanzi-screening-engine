"""POST /v1/report: off by default, worker view only, same request as /v1/screen, never changes the rules, no HIV information."""
import json

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, SAM_BASE, need_api
from tests.childreport.test_build import PRETERM
from tests.prediction.test_model import _spec, children, pre  # noqa: F401  (fixtures)
from thanzi_screen.prediction import PredictionModel

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402
from thanzi_screen.schemas import ChildReportResponse  # noqa: E402

GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}
PREV = {"age_days": 400, "weight_kg": 9.0, "length_height_cm": 74.0, "measure_position": "length"}


def _client(**kw):
    return TestClient(create_app(gateway_key=GW, **kw))


def _on(**kw):
    return _client(child_report=True, **kw)


def test_off_by_default():
    r = _client().post("/v1/report", json=LOW_BASE, headers=HG)
    assert r.status_code == 404 and r.json()["code"] == "report_off"


def test_environment_switch(monkeypatch):
    monkeypatch.setenv("THANZI_CHILD_REPORT_ENABLED", "1")
    assert _client().post("/v1/report", json=LOW_BASE, headers=HG).status_code == 200
    monkeypatch.setenv("THANZI_CHILD_REPORT_ENABLED", "0")
    assert _client().post("/v1/report", json=LOW_BASE, headers=HG).status_code == 404


def test_needs_the_gateway_key_and_refuses_unknown_fields():
    c = _on()
    assert c.post("/v1/report", json=LOW_BASE).status_code == 401
    assert c.post("/v1/report", json=LOW_BASE, headers={"X-Gateway-Key": "wrong-key-0123456789"}).status_code == 401
    bad = c.post("/v1/report", json={**LOW_BASE, "child_name": "x"}, headers=HG)
    assert bad.status_code == 422 and bad.json()["code"] == "unknown_field"
    assert c.post("/v1/report", json={"sex": "male"}, headers=HG).status_code == 422


def test_there_is_no_audit_version_of_the_report():
    """The audit key changes nothing: the report is built from the worker view only."""
    c = TestClient(create_app(gateway_key=GW, audit_key="audit-key-0123456789", child_report=True))
    plain = c.post("/v1/report", json=MAM_BASE, headers=HG).json()
    with_key = c.post("/v1/report?view=audit", json=MAM_BASE, headers={**HG, "X-Audit-Key": "audit-key-0123456789"}).json()
    assert plain == with_key and "explanation" not in plain and "referral_text" not in json.dumps(plain)


@pytest.mark.parametrize("body", [SAM_BASE, MAM_BASE, LOW_BASE, {**LOW_BASE, "previous_measurement": PREV}, PRETERM],
                         ids=["sam", "mam", "low", "low_growth", "preterm"])
def test_report_matches_the_screening_response_and_the_contract(body):
    c = _on()
    screened = c.post("/v1/screen", json=body, headers=HG).json()
    r = c.post("/v1/report", json=body, headers=HG)
    assert r.status_code == 200
    report = r.json()
    ChildReportResponse.model_validate(report)                          # the committed schema describes what is returned
    assert report["result"]["tier"] == screened["tier"]
    assert report["result"]["summary"] == screened["worker_summary"]
    if "classification" in screened:
        assert report["result"]["classification"] == screened["classification"]
        assert report["result"]["programme"] == screened["programme"]
        assert report["result"]["rules_fired"] == screened["rules_fired"]


def test_screening_response_is_identical_with_the_report_on_or_off():
    a = _client().post("/v1/screen", json=SAM_BASE, headers=HG).json()
    b = _on().post("/v1/screen", json=SAM_BASE, headers=HG).json()
    assert a == b


@pytest.mark.parametrize("body", [SAM_BASE, MAM_BASE, LOW_BASE, PRETERM])
def test_no_hiv_information_in_any_report(body):
    for hiv in (True, False, None):
        text = _on().post("/v1/report", json={**body, "hiv_positive": hiv}, headers=HG).text.lower()
        assert "hiv" not in text


def test_hidden_programme_stays_hidden_in_the_report():
    c = _on()
    a = c.post("/v1/report", json={**MAM_BASE, "hiv_positive": True}, headers=HG).json()
    b = c.post("/v1/report", json={**MAM_BASE, "hiv_positive": False}, headers=HG).json()
    assert a == b and a["result"]["programme"] is None


def test_engine_errors_are_the_same_422_as_screen():
    c = _on()
    body = {**LOW_BASE, "weight_kg": -1}
    s, r = c.post("/v1/screen", json=body, headers=HG), c.post("/v1/report", json=body, headers=HG)
    assert s.status_code == r.status_code == 422 and s.json() == r.json()
    assert "-1" not in r.text                                            # never echoes submitted values


def test_with_a_prediction_model_the_report_gains_a_status_and_the_rules_do_not_move(pre):  # noqa: F811
    model = PredictionModel(_spec(pre))
    body = {**LOW_BASE, "previous_measurement": PREV}
    plain = _on().post("/v1/report", json=body, headers=HG).json()
    withp = _on(prediction_model=model).post("/v1/report", json=body, headers=HG).json()
    assert plain["prediction"]["status"] == "not_run"
    assert withp["prediction"]["status"] in ("concern", "no_concern", "not_scored")
    assert withp["result"] == plain["result"] and withp["action"] == plain["action"]
    rank = {"routine": 0, "raised": 1, "recheck": 2, "urgent": 3}
    assert rank[withp["attention"]["level"]] >= rank[plain["attention"]["level"]]
    if withp["prediction"]["status"] != "concern":
        assert "not reassurance" in withp["prediction"]["statement"]


def test_the_route_is_counted_and_listed():
    c = _on()
    c.post("/v1/report", json=LOW_BASE, headers=HG)
    about = c.get("/v1/about", headers=HG).json()
    assert "/v1/report" in about["routes"]
    assert c.get("/v1/metrics", headers=HG).json()["by_route"]["/v1/report"] == 1
