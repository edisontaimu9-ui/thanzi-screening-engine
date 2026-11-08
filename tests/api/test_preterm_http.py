"""Preterm routing over HTTP: contract, access, errors, OpenAPI (needs FastAPI)."""
import json

from tests.api._support import MAM_BASE, need_api

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api import service  # noqa: E402
from thanzi_screen.api.app import create_app  # noqa: E402
from thanzi_screen.ml import load_models  # noqa: E402

GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"
HG, HA = {"X-Gateway-Key": GW}, {"X-Audit-Key": AU}
PRE = {"sex": "female", "age_days": 20, "weight_kg": 1.25, "length_height_cm": 38.0, "measure_position": "length",
       "oedema": "none", "danger_signs": [], "complications": [], "gestational_age_weeks": 29, "birth_weight_g": 1100,
       "hc_cm": 27.0, "consecutive_days_gaining_weight": 2}


def client():
    return TestClient(create_app(models=load_models(), gateway_key=GW, audit_key=AU), raise_server_exceptions=False)


def test_preterm_request_is_routed_automatically_and_matches_the_core():
    c = client()
    r = c.post("/v1/screen", json=PRE, headers=HG)
    assert r.status_code == 200
    body = r.json()
    assert body["route"] == "preterm" and body["preterm_level"] == "refer" and body["tier"] == "mam"
    assert body["measurements"]["weight"]["z"] == -1.99 and body["birth_context"]["pma_weeks"] == 31.86
    assert body == json.loads(json.dumps(service.screen(PRE, "worker", None)))
    assert "engine_output" not in body and "CC BY-NC-ND 4.0" in body["data_attribution"]


def test_audit_view_needs_the_audit_key_and_adds_the_engine_output():
    c = client()
    assert c.post("/v1/screen?view=audit", json=PRE, headers=HG).status_code == 403
    r = c.post("/v1/screen?view=audit", json=PRE, headers={**HG, **HA})
    assert r.status_code == 200 and "engine_output" in r.json() and "ml_features" in r.json()
    assert r.json()["ml_features"]["z_length"] is not None


def test_requests_without_birth_context_are_unchanged():
    r = client().post("/v1/screen", json=MAM_BASE, headers=HG)
    assert r.status_code == 200 and "route" not in r.json()


def test_validation_is_strict_and_never_echoes_values():
    c = client()
    for change in ({"gestational_age_weeks": "29"}, {"birth_weight_g": True}, {"neonatal_danger_signs": ["nonsense"]},
                   {"consecutive_days_gaining_weight": 1.5}, {"sick": "yes"}):
        r = c.post("/v1/screen", json={**PRE, **change}, headers=HG)
        assert r.status_code == 422 and "nonsense" not in r.text
    r = c.post("/v1/screen", json={**PRE, "gestational_age_weeks": 12}, headers=HG)
    assert r.status_code == 422 and r.json()["code"] == "invalid_input"
    r = c.post("/v1/screen", json={**PRE, "gestational_age_weeks": 30, "birth_weight_g": None}, headers=HG)
    assert r.status_code == 422 and r.json()["code"] == "invalid_input"
    r = c.post("/v1/screen", json={**PRE, "measure_position": "height"}, headers=HG)
    assert r.status_code == 422


def test_openapi_documents_the_preterm_fields_and_responses():
    spec = create_app(models=load_models(), gateway_key=GW).openapi()
    props = spec["components"]["schemas"]["ScreenRequest"]["properties"]
    assert {"gestational_age_weeks", "birth_weight_g", "neonatal_danger_signs"} <= set(props)
    assert {"PretermResponse", "PretermAuditResponse", "BirthContext"} <= set(spec["components"]["schemas"])
