"""GET /v1/about and GET /v1/metrics (D176): behind the gateway key, honest about components, counts only, no child data."""
import json

import pytest

from tests.api._support import MAM_BASE, need_api

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api import metrics as metrics_mod  # noqa: E402
from thanzi_screen.api.app import create_app  # noqa: E402
from thanzi_screen.llm import LLMClient, LLMConfig  # noqa: E402
from thanzi_screen.llm.providers import MockProvider  # noqa: E402
from thanzi_screen.ml import load_models  # noqa: E402

GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in [k for k in __import__("os").environ if k.startswith("THANZI_LLM_")]:
        monkeypatch.delenv(name, raising=False)


def make(models, **kw):
    return TestClient(create_app(models=models, gateway_key=GW, **kw), raise_server_exceptions=False)


def comps(body):
    return {c["name"]: c for c in body["components"]}


# ---- access ----
@pytest.mark.parametrize("path", ["/v1/about", "/v1/metrics"])
def test_both_routes_need_the_gateway_key(models, path):
    c = make(models)
    for headers in ({}, {"X-Gateway-Key": "wrong-wrong-wrong-wrong"}, {"X-Gateway-Key": ""}):
        r = c.get(path, headers=headers)
        assert r.status_code == 401 and r.json() == {"code": "unauthorised", "message": "Unauthorised."}
    assert c.get(path, headers=HG).status_code == 200


def test_health_still_returns_only_status(models):
    assert make(models).get("/health").json() == {"status": "ok"}


# ---- about ----
def test_about_reports_versions_and_components(models):
    c = make(models)
    b = c.get("/v1/about", headers=HG).json()
    v = c.get("/version", headers=HG).json()
    for key in ("api_version", "engine_version", "rule_set_version", "status", "disclaimer"):
        assert b[key] == v[key]
    assert b["health"] == "ok" and b["uptime_seconds"] >= 0
    assert [x["name"] for x in b["components"]] == ["screening_engine", "ml_logistic", "ml_deep", "ml_risk", "ml_prediction", "growth_monitoring", "llm_service", "child_report", "surveillance_reports"]
    k = comps(b)
    assert k["ml_logistic"]["state"] == "ok" and k["ml_logistic"]["version"] == models.version
    assert k["ml_deep"]["state"] == "ok" and k["ml_deep"]["version"] == v["deep_model_version"]
    assert k["llm_service"]["state"] == "off"
    assert "/v1/screen" in b["routes"] and "/v1/about" in b["routes"] and not any(r.startswith("/v1/llm") for r in b["routes"])


def test_about_in_degraded_mode_says_so(models, monkeypatch):
    monkeypatch.setenv("THANZI_MODELS_DIR", "/nonexistent-models-dir")
    c = TestClient(create_app(gateway_key=GW, deep_models=None), raise_server_exceptions=False)
    b = c.get("/v1/about", headers=HG).json()
    k = comps(b)
    assert b["health"] == "degraded" == c.get("/health").json()["status"]
    assert k["ml_logistic"]["state"] == "degraded" and k["ml_logistic"]["version"] is None
    assert k["screening_engine"]["state"] == "ok"             # the rules never depend on the models


def test_about_deep_off(models, monkeypatch):
    monkeypatch.setenv("THANZI_DEEP_ENABLED", "0")
    k = comps(make(models).get("/v1/about", headers=HG).json())
    assert k["ml_deep"]["state"] == "off" and k["ml_deep"]["version"] is None and k["ml_logistic"]["state"] == "ok"


def test_about_with_llm_enabled_never_calls_the_model_server_or_shows_its_address(models):
    config = LLMConfig(provider="mock", endpoint="http://10.1.2.3:9999", retry_backoff_s=0.0)
    provider = MockProvider(config)
    calls = []
    original = provider.health

    async def spy():
        calls.append(1)
        return await original()
    provider.health = spy
    c = make(models, llm=LLMClient(config, provider))
    r = c.get("/v1/about", headers=HG)
    k = comps(r.json())
    assert k["llm_service"]["state"] == "ok" and k["llm_service"]["version"] == config.model
    assert "/v1/llm/health" in r.json()["routes"] and "/v1/llm/health" in k["llm_service"]["detail"]
    assert calls == []                                          # about never touches the LLM server
    assert "10.1.2.3" not in r.text


# ---- metrics ----
def test_metrics_start_empty_and_have_a_stable_shape(models):
    b = make(models).get("/v1/metrics", headers=HG).json()
    assert b["scope"] == "process" and b["requests_total"] == 0 and b["by_route"] == {} and b["by_status"] == {}
    assert make(models).get("/v1/metrics", headers=HG).json()["requests_total"] == 0     # a call counts from the next read
    assert b["screen_latency"] == {"calls_measured": 0, "window": metrics_mod.LATENCY_WINDOW,
                                   "p50_ms": None, "p95_ms": None, "max_ms": None, "mean_ms": None}


def test_metrics_count_routes_statuses_and_screen_latency(models):
    c = make(models)
    c.get("/health")
    c.get("/version")                                           # 401, no key
    for _ in range(3):
        assert c.post("/v1/screen", json=MAM_BASE, headers=HG).status_code == 200
    assert c.post("/v1/screen", json={"name": "x"}, headers=HG).status_code == 422
    b = c.get("/v1/metrics", headers=HG).json()
    assert b["by_route"] == {"/health": 1, "/version": 1, "/v1/screen": 4}          # this read counts from the next one
    assert b["by_status"]["200"] == 4 and b["by_status"]["401"] == 1 and b["by_status"]["422"] == 1
    assert b["requests_total"] == sum(b["by_status"].values()) == 6 and b["server_errors"] == 0
    assert c.get("/v1/metrics", headers=HG).json()["by_route"]["/v1/metrics"] == 1
    s = b["screen_latency"]
    assert s["calls_measured"] == 4 and 0 < s["p50_ms"] <= s["p95_ms"] <= s["max_ms"]


def test_refused_and_unknown_requests_are_counted_without_growing_the_table(models):
    c = make(models)
    for i in range(30):
        c.get(f"/made-up-{i}", headers=HG)
        c.get(f"/made-up-{i}")
    b = c.get("/v1/metrics", headers=HG).json()
    assert b["by_route"] == {"other": 60}
    assert b["by_status"]["401"] == 30 and b["by_status"]["404"] == 30


def test_a_server_error_is_counted(models, monkeypatch):
    from thanzi_screen.api import service

    def boom(*a, **k):
        raise RuntimeError("secret internal detail")
    monkeypatch.setattr(service, "screen", boom)
    c = make(models)
    assert c.post("/v1/screen", json=MAM_BASE, headers=HG).status_code == 500
    b = c.get("/v1/metrics", headers=HG).json()
    assert b["by_status"]["500"] == 1 and b["server_errors"] == 1


def test_nothing_about_a_child_reaches_about_or_metrics(models):
    c = make(models)
    marker = {**MAM_BASE, "weight_kg": 9.8765, "muac_cm": 12.3456, "length_height_cm": 77.7771}
    c.post("/v1/screen", json=marker, headers=HG)
    c.post("/v1/screen", json={**marker, "name": "Chikondi Banda", "child_id": "MW-998877"}, headers=HG)
    text = c.get("/v1/metrics", headers=HG).text + c.get("/v1/about", headers=HG).text
    for secret in ("9.8765", "12.3456", "77.7771", "Chikondi", "MW-998877", GW, "testserver", "127.0.0.1"):
        assert secret not in text


# ---- the counter itself ----
def test_percentiles_use_nearest_rank_over_a_bounded_window():
    m = metrics_mod.Metrics()
    for ms in range(1, 2001):                                   # 1..2000 ms: only the last 1000 are kept
        m.record("/v1/screen", 200, ms / 1000)
    s = m.snapshot()["screen_latency"]
    assert s["calls_measured"] == 1000 and s["max_ms"] == 2000.0
    assert s["p50_ms"] == 1500.0 and s["p95_ms"] == 1950.0 and s["mean_ms"] == 1500.5
    assert m.snapshot()["requests_total"] == 2000


def test_the_snapshot_is_json_safe_and_uptime_follows_the_clock():
    ticks = iter([100.0, 100.0, 107.5])
    m = metrics_mod.Metrics(clock=lambda: 1_000.0, monotonic=lambda: next(ticks))
    assert json.dumps(m.snapshot()) and m.snapshot()["since"] == 1_000.0


def test_openapi_describes_both_routes_with_the_gateway_key(models):
    schema = create_app(models=models, gateway_key=GW).openapi()
    for path in ("/v1/about", "/v1/metrics"):
        op = schema["paths"][path]["get"]
        assert op["security"] == [{"GatewayKey": []}] and "200" in op["responses"]
