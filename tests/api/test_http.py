"""HTTP edge: access control, contract, errors, degraded mode, drift guard (D78-D84)."""
import json
import logging
from pathlib import Path

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, SAM_BASE, need_api

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api import security, service  # noqa: E402
from thanzi_screen.api.app import create_app  # noqa: E402
from thanzi_screen.api.security import ConfigError  # noqa: E402
from thanzi_screen.ml import load_models  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"
HG, HA = {"X-Gateway-Key": GW}, {"X-Audit-Key": AU}


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture()
def client(models):
    return TestClient(create_app(models=models, gateway_key=GW, audit_key=AU), raise_server_exceptions=False)


def post(c, body=None, view=None, headers=HG, **kw):
    url = "/v1/screen" + (f"?view={view}" if view else "")
    return c.post(url, json=MAM_BASE if body is None else body, headers=headers, **kw)


# ---- access ----
def test_every_route_but_health_needs_the_gateway_key(client):
    for method, path in (("get", "/version"), ("post", "/v1/screen"), ("get", "/docs"), ("get", "/openapi.json"),
                         ("get", "/redoc"), ("get", "/nope"), ("delete", "/v1/screen"), ("post", "/v1/screen?view=audit")):
        r = getattr(client, method)(path)
        assert r.status_code == 401, path
        assert r.json() == {"code": "unauthorised", "message": "Unauthorised."}
        assert "www-authenticate" not in r.headers


def test_wrong_empty_and_audit_key_as_gateway_key_are_refused(client):
    for bad in ({"X-Gateway-Key": "wrong-wrong-wrong-wrong"}, {"X-Gateway-Key": ""}, {"X-Gateway-Key": AU}, {}):
        assert client.get("/version", headers=bad).status_code == 401
        assert client.post("/v1/screen", json=MAM_BASE, headers=bad).status_code == 401


def test_unauthenticated_callers_learn_nothing_from_validation(client):
    r = client.post("/v1/screen", content="{not json", headers={"content-type": "application/json"})
    assert r.status_code == 401
    assert client.post("/v1/screen", json={"name": "x"}).status_code == 401


def test_health_needs_no_key_and_returns_nothing_else(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_version_with_key(client, models):
    r = client.get("/version", headers=HG)
    assert r.status_code == 200
    assert r.json()["model_version"] == models.version and r.json()["rule_set_version"] == "rules_v2016"


def test_audit_view_needs_its_own_key(client):
    assert post(client, view="audit").status_code == 403
    assert post(client, view="audit", headers={**HG, "X-Audit-Key": "wrong-wrong-wrong-wrong"}).status_code == 403
    assert post(client, view="audit", headers={**HG, "X-Audit-Key": GW}).status_code == 403
    ok = post(client, view="audit", headers={**HG, **HA})
    assert ok.status_code == 200 and ok.json()["view"] == "audit"
    assert post(client, view="audit", headers=HA).status_code == 401            # audit key alone is not enough
    assert post(client, headers={**HG, **HA}).json()["view"] == "worker"       # key does not switch the view by itself


def test_audit_is_off_when_no_audit_key_is_configured(models):
    c = TestClient(create_app(models=models, gateway_key=GW), raise_server_exceptions=False)
    r = post(c, view="audit", headers={**HG, **HA})
    assert r.status_code == 403 and r.json()["code"] == "audit_forbidden"
    assert post(c).status_code == 200


def test_startup_fails_closed(monkeypatch):
    monkeypatch.delenv("THANZI_GATEWAY_KEY", raising=False)
    monkeypatch.delenv("THANZI_DEV_MODE", raising=False)
    with pytest.raises(ConfigError):
        create_app()
    with pytest.raises(ConfigError):
        create_app(gateway_key="", audit_key=AU)
    from thanzi_screen.api.app import create_app_from_env
    with pytest.raises(ConfigError):
        create_app_from_env()
    monkeypatch.setenv("THANZI_GATEWAY_KEY", GW)
    assert TestClient(create_app_from_env()).get("/version", headers=HG).status_code == 200


def test_docs_routes_are_off_outside_dev_mode(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path, headers=HG).status_code == 404


def test_dev_mode_without_key_serves_docs_and_screens(models, monkeypatch):
    monkeypatch.delenv("THANZI_GATEWAY_KEY", raising=False)
    c = TestClient(create_app(models=models, dev_mode=True))
    assert c.get("/docs").status_code == 200 and c.get("/openapi.json").status_code == 200
    assert c.post("/v1/screen", json=MAM_BASE).status_code == 200


def test_dev_mode_with_a_key_still_enforces_it(models):
    c = TestClient(create_app(models=models, gateway_key=GW, dev_mode=True))
    assert c.post("/v1/screen", json=MAM_BASE).status_code == 401


def test_no_cors_headers(client):
    r = client.options("/v1/screen", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST",
                                              **HG})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in post(client, headers={**HG, "Origin": "https://evil.example"}).headers


def test_oversized_body_is_refused_after_auth(client):
    big = json.dumps({**MAM_BASE, "x": "a" * 20000})
    assert client.post("/v1/screen", content=big, headers={**HG, "content-type": "application/json"}).status_code == 413
    assert client.post("/v1/screen", content=big, headers={"content-type": "application/json"}).status_code == 401


# ---- contract ----
def test_worker_view_by_default_matches_the_core(client, models):
    r = post(client)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    assert r.json() == service.screen(MAM_BASE, "worker", models, client.app.state.deep)
    assert post(client, view="worker").json() == r.json()


def test_hiv_never_appears_in_any_worker_response_over_http(client):
    for hiv in (True, False, None):
        for base in (MAM_BASE, SAM_BASE, LOW_BASE, {**MAM_BASE, "appetite": "failed"}):
            r = post(client, {**base, "hiv_positive": hiv})
            assert r.status_code == 200 and "hiv" not in r.text.lower()
    assert "referral_text" not in post(client).json()


def test_hiv_appears_only_in_the_audit_view(client):
    r = post(client, {**MAM_BASE, "hiv_positive": True}, view="audit", headers={**HG, **HA})
    assert r.json()["programme"] == "OTP" and "MAM.HIV_OTP" in r.json()["rules_fired"]
    assert "HIV" in r.text


def test_null_and_empty_list_survive_json(client):
    a = post(client, {**SAM_BASE, "danger_signs": [], "complications": []}).json()
    b = post(client, {**SAM_BASE, "danger_signs": None, "complications": None}).json()
    assert a["classification"] == "SAM_OTP" and b["classification"] == "SAM_ASSESS"


@pytest.mark.parametrize("extra", [{"name": "Secret Person"}, {"child_id": "C-9"}, {"date_of_birth": "2024-01-01"}])
def test_identifying_fields_are_rejected_without_echo(client, extra):
    r = post(client, {**MAM_BASE, **extra})
    assert r.status_code == 422 and r.json()["code"] == "unknown_field"
    for needle in ("Secret", "C-9", "2024-01-01", "child_id", "date_of_birth"):
        assert needle not in r.text


@pytest.mark.parametrize("change", [{"weight_kg": "SECRET-VALUE"}, {"sex": "SECRET-VALUE"}, {"age_days": 5.5},
                                    {"age_days": True}, {"danger_signs": ["SECRET-VALUE"]}, {"hiv_positive": "SECRET-VALUE"},
                                    {"weight_kg": -5}, {"muac_cm": 0}])
def test_validation_and_engine_errors_are_422_and_never_echo(client, change):
    r = post(client, {**MAM_BASE, **change})
    assert r.status_code == 422 and r.json()["code"] in ("invalid_request", "invalid_input")
    assert "SECRET-VALUE" not in r.text


def test_missing_required_fields_and_bad_json(client):
    r = post(client, {k: v for k, v in MAM_BASE.items() if k != "oedema"})
    assert r.status_code == 422 and r.json()["fields"] == ["oedema"]
    r = client.post("/v1/screen", content="{bad SECRET-VALUE", headers={**HG, "content-type": "application/json"})
    assert r.status_code == 422 and r.json()["code"] == "invalid_json" and "SECRET-VALUE" not in r.text
    assert client.post("/v1/screen", json=[1, 2], headers=HG).status_code == 422


def test_invalid_view_is_422(client):
    r = post(client, view="everything")
    assert r.status_code == 422 and r.json()["fields"] == ["view"]


def test_unexpected_error_is_generic_with_no_input_or_trace(models, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("SECRET-INTERNAL 7.7777 stack detail")
    monkeypatch.setattr(service, "screen", boom)
    c = TestClient(create_app(models=models, gateway_key=GW), raise_server_exceptions=False)
    with caplog.at_level(logging.DEBUG):
        r = post(c, {**MAM_BASE, "weight_kg": 7.7777})
    assert r.status_code == 500 and r.json() == {"code": "internal_error", "message": "Internal error."}
    assert "SECRET-INTERNAL" not in r.text and "Traceback" not in r.text and "7.7777" not in r.text
    assert "SECRET-INTERNAL" not in caplog.text and "7.7777" not in caplog.text


def test_no_request_values_in_logs(client, caplog):
    body = {**MAM_BASE, "weight_kg": 11.3579, "length_height_cm": 80.2468, "muac_cm": 12.0135}
    with caplog.at_level(logging.DEBUG):
        assert post(client, body).status_code == 200
        assert post(client, {**body, "name": "Zuzu-Secret-Name"}).status_code == 422
        assert post(client, {**body, "weight_kg": -2.4681}).status_code == 422
    for needle in ("11.3579", "80.2468", "12.0135", "Zuzu-Secret-Name", "2.4681", GW):
        assert needle not in caplog.text


# ---- degraded mode (D79) ----
def test_missing_models_start_degraded_and_still_screen(tmp_path, models):
    c = TestClient(create_app(gateway_key=GW, models_dir=tmp_path), raise_server_exceptions=False)
    assert c.get("/health").json() == {"status": "degraded"}
    assert c.get("/version", headers=HG).json()["model_version"] == "none"
    r = post(c, SAM_BASE)
    assert r.status_code == 200 and r.json()["ml_flags"]["available"] is False
    full = TestClient(create_app(models=models, gateway_key=GW)).post("/v1/screen", json=SAM_BASE, headers=HG).json()
    assert r.json()["classification"] == full["classification"] and r.json()["tier"] == full["tier"]


def test_mismatched_models_start_degraded(tmp_path):
    src = ROOT / "models"
    for name in ("recording_error_lr.json", "recording_field_tree.json"):
        d = json.loads((src / name).read_text())
        d["metadata"]["feature_names"] = d["metadata"]["feature_names"][:-1]
        (tmp_path / name).write_text(json.dumps(d))
    c = TestClient(create_app(gateway_key=GW, models_dir=tmp_path))
    assert c.get("/health").json() == {"status": "degraded"}
    assert post(c).status_code == 200


# ---- OpenAPI contract ----
def test_openapi_file_matches_the_live_app(models):
    live = create_app(models=models, gateway_key=GW).openapi()
    committed = json.loads((ROOT / "docs/api/openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(live)), "run: python scripts/export_openapi.py"


def test_openapi_documents_security_and_hides_nothing_secret(models):
    spec = create_app(models=models, gateway_key=GW).openapi()
    assert spec["components"]["securitySchemes"]["GatewayKey"]["name"] == "X-Gateway-Key"
    assert "security" not in spec["paths"]["/health"]["get"]
    assert spec["paths"]["/v1/screen"]["post"]["security"] == [{"GatewayKey": []}]
    text = json.dumps(spec)
    assert GW not in text and AU not in text
    assert set(spec["components"]["schemas"]["ScreenRequest"]["properties"]) == set(service.ALLOWED)
    assert spec["components"]["schemas"]["ScreenRequest"]["additionalProperties"] is False
    assert "name" not in spec["components"]["schemas"]["ScreenRequest"]["properties"]
