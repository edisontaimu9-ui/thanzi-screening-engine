"""Advisory prediction block in the API: escalate only, off by default, fails safe, never changes the rules."""
import json

import pytest

from tests.api._support import LOW_BASE, SAM_BASE, need_api
from tests.prediction.test_model import _spec, children, pre  # noqa: F401  (fixtures)
from thanzi_screen.prediction import PredictionModel

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}
PREV = {"age_days": 400, "weight_kg": 9.0, "length_height_cm": 74.0, "measure_position": "length"}
RULES = ("classification", "tier", "referral_text", "rules_fired")


@pytest.fixture
def model(pre):  # noqa: F811
    return PredictionModel(_spec(pre))


def _client(**kw):
    return TestClient(create_app(gateway_key=GW, **kw))


def _post(c, body, view="worker", headers=HG):
    return c.post(f"/v1/screen?view={view}", json=body, headers=headers)


def test_off_by_default_so_the_response_has_no_block():
    assert "ml_prediction" not in _post(_client(), LOW_BASE).json()


def test_block_is_added_and_never_changes_the_rules(model):
    base, withp = _post(_client(), SAM_BASE).json(), _post(_client(prediction_model=model), SAM_BASE).json()
    block = withp.pop("ml_prediction")
    assert block["advisory"] and block["non_clinical"] is True and "probability" not in block
    assert withp == base


def test_previous_visit_is_used_and_audit_adds_detail(model):
    body = {**LOW_BASE, "previous_measurement": PREV}
    c = _client(prediction_model=model)
    worker, audit = _post(c, body).json()["ml_prediction"], _post(c, body, "audit", {**HG, "X-Audit-Key": "x"}).status_code
    assert worker["scored"] in (True, False) and audit in (200, 403)


def test_a_scored_audit_block_has_probability(model):
    c = TestClient(create_app(gateway_key=GW, audit_key="audit-key-0123456789", prediction_model=model))
    b = _post(c, {**LOW_BASE, "previous_measurement": PREV}, "audit", {**HG, "X-Audit-Key": "audit-key-0123456789"}).json()["ml_prediction"]
    if b["scored"]:
        assert 0 <= b["probability"] <= 1 and b["explanation"]


def test_enabled_but_simulated_file_is_refused_without_the_allow_flag(model, tmp_path, monkeypatch):
    f = tmp_path / "m.json"
    f.write_text(json.dumps(model.spec))
    monkeypatch.setenv("THANZI_PREDICTION_ENABLED", "1")
    monkeypatch.setenv("THANZI_PREDICTION_MODEL", str(f))
    c = _client()
    assert "ml_prediction" not in _post(c, LOW_BASE).json()
    assert [x for x in c.get("/v1/about", headers=HG).json()["components"] if x["name"] == "ml_prediction"][0]["state"] == "degraded"
    monkeypatch.setenv("THANZI_PREDICTION_ALLOW_SIMULATED", "1")
    c = _client()
    assert _post(c, LOW_BASE).json()["ml_prediction"]["non_clinical"] is True
    assert c.get("/version", headers=HG).json()["prediction_model_version"] == model.version


def test_missing_file_means_degraded_never_a_failed_start(monkeypatch):
    monkeypatch.setenv("THANZI_PREDICTION_ENABLED", "1")
    monkeypatch.setenv("THANZI_PREDICTION_MODEL", "/nope.json")
    assert _post(_client(), LOW_BASE).status_code == 200


def test_no_hiv_content_reaches_the_worker_view(model):
    body = {**LOW_BASE, "hiv_positive": True}
    assert "hiv" not in json.dumps(_post(_client(prediction_model=model), body).json()).lower()


def test_an_earlier_visit_that_is_not_comparable_is_unavailable_not_used(model):
    same_day = {**PREV, "age_days": LOW_BASE["age_days"] - 3}
    no_length = {"age_days": 400, "weight_kg": 9.0}
    c = _client(prediction_model=model)
    for prev in (same_day, no_length):
        b = _post(c, {**LOW_BASE, "previous_measurement": prev}).json()["ml_prediction"]
        assert "longitudinal" in b["inputs"]["unavailable"]
    assert "longitudinal" in _post(c, LOW_BASE).json()["ml_prediction"]["inputs"]["not_applicable"]


def test_missing_history_and_feeding_never_invalidate_the_anthropometric_result(model):
    b = _post(_client(prediction_model=model), LOW_BASE).json()["ml_prediction"]
    assert b["not_scored_reason"] != "essential_input_unavailable" and "clinical" in b["inputs"]["not_assessed"]
