"""Optional LLM routes (D128-D133): off by default, behind the gateway key, error mapping, and no effect on screening."""
import logging
import socket

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, SAM_BASE, need_api
from tests.llm._support import SYNTHETIC_MARKER, SYNTHETIC_PROMPT

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402
from thanzi_screen.llm import (LLMAuthError, LLMBusyError, LLMClient, LLMConfig, LLMConfigError, LLMConnectionError,  # noqa: E402
                               LLMModelNotFoundError, LLMRejectedError, LLMResponseError, LLMServerError, LLMTimeoutError)
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


def mock_client(**provider_kwargs):
    config = LLMConfig(provider="mock", retry_backoff_s=0.0)
    return LLMClient(config, MockProvider(config, **provider_kwargs))


def app_with(models, client=None, **kw):
    return TestClient(create_app(models=models, gateway_key=GW, llm=client, **kw), raise_server_exceptions=False)


def dead_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return "http://127.0.0.1:%d" % s.getsockname()[1]


# ---- off by default ----
def test_routes_do_not_exist_when_disabled(models):
    c = app_with(models)
    assert c.get("/v1/llm/health", headers=HG).status_code == 404
    assert c.post("/v1/llm/generate", json={"prompt": "x"}, headers=HG).status_code == 404
    dev = TestClient(create_app(models=models, dev_mode=True))
    assert not [p for p in dev.get("/openapi.json").json()["paths"] if "llm" in p]


def test_other_env_settings_do_not_enable_it(models, monkeypatch):
    monkeypatch.setenv("THANZI_LLM_PROVIDER", "mock")
    monkeypatch.setenv("THANZI_LLM_ENABLED", "true")             # only exactly "1" counts
    assert app_with(models).get("/v1/llm/health", headers=HG).status_code == 404


def test_env_enables_and_bad_config_fails_closed(models, monkeypatch):
    monkeypatch.setenv("THANZI_LLM_ENABLED", "1")
    monkeypatch.setenv("THANZI_LLM_PROVIDER", "mock")
    assert app_with(models).get("/v1/llm/health", headers=HG).json()["provider"] == "mock"
    monkeypatch.setenv("THANZI_LLM_ENDPOINT", "https://api.example.com")       # remote without allow_remote
    with pytest.raises(LLMConfigError):
        create_app(models=models, gateway_key=GW)


# ---- access ----
def test_gateway_key_is_required(models):
    c = app_with(models, mock_client())
    for method, path in (("get", "/v1/llm/health"), ("post", "/v1/llm/generate")):
        assert getattr(c, method)(path).status_code == 401
        assert getattr(c, method)(path, headers={"X-Gateway-Key": "wrong-key-0123456789"}).status_code == 401


def test_routes_appear_in_openapi_with_the_gateway_scheme(models):
    spec = TestClient(create_app(models=models, dev_mode=True, llm=mock_client())).get("/openapi.json").json()
    assert spec["paths"]["/v1/llm/generate"]["post"]["security"] == [{"GatewayKey": []}]
    assert "/v1/llm/health" in spec["paths"]


# ---- behaviour ----
def test_generate_returns_text_with_the_notice(models):
    r = app_with(models, mock_client(reply="Synthetic answer.")).post(
        "/v1/llm/generate", json={"prompt": SYNTHETIC_PROMPT, "system": "Be brief.", "max_tokens": 32, "temperature": 0.0}, headers=HG)
    body = r.json()
    assert r.status_code == 200 and body["text"] == "Synthetic answer." and body["provider"] == "mock"
    assert "not a screening result" in body["notice"] and set(body) >= {"model", "finish_reason", "latency_ms"}


def test_request_overrides_reach_the_provider(models):
    client = mock_client()
    app_with(models, client).post("/v1/llm/generate", json={"prompt": "x", "max_tokens": 77, "temperature": 0.9}, headers=HG)
    params = client.provider.calls[0][1]
    assert (params.max_tokens, params.temperature) == (77, 0.9)


@pytest.mark.parametrize("body", [{}, {"prompt": ""}, {"prompt": "x" * 4001}, {"prompt": "x", "max_tokens": 5000},
                                  {"prompt": "x", "temperature": 5}, {"prompt": "x", "model": "other"},
                                  {"prompt": "x", "stream": True}, {"prompt": "x", "system": ""}])
def test_invalid_bodies_are_422_with_a_stable_shape(models, body):
    r = app_with(models, mock_client()).post("/v1/llm/generate", json=body, headers=HG)
    assert r.status_code == 422 and set(r.json()) <= {"code", "message", "fields"}


@pytest.mark.parametrize("error,status,code", [
    (LLMTimeoutError(), 504, "llm_timeout"), (LLMBusyError(), 503, "llm_busy"), (LLMConnectionError(), 503, "llm_unreachable"),
    (LLMModelNotFoundError(), 503, "llm_model_not_found"), (LLMAuthError(), 503, "llm_auth"), (LLMServerError(500), 503, "llm_server_error"),
    (LLMResponseError(), 502, "llm_bad_response"), (LLMRejectedError(400), 502, "llm_rejected")])
def test_model_errors_map_to_stable_codes(models, error, status, code):
    r = app_with(models, mock_client(fail_with=error)).post("/v1/llm/generate", json={"prompt": SYNTHETIC_PROMPT}, headers=HG)
    assert (r.status_code, r.json()["code"]) == (status, code) and SYNTHETIC_MARKER not in r.text
    assert ("Retry-After" in r.headers) == (code == "llm_busy")


def test_prompt_too_long_for_the_client_limit_is_422(models):
    config = LLMConfig(provider="mock", max_prompt_chars=20)
    client = LLMClient(config, MockProvider(config))
    r = app_with(models, client).post("/v1/llm/generate", json={"prompt": "x" * 30}, headers=HG)
    assert (r.status_code, r.json()["code"]) == (422, "llm_bad_request")


def test_llm_health_codes(models):
    assert app_with(models, mock_client()).get("/v1/llm/health", headers=HG).status_code == 200
    down = app_with(models, mock_client(fail_with=LLMConnectionError())).get("/v1/llm/health", headers=HG)
    assert down.status_code == 503 and down.json()["state"] == "unavailable" and down.json()["detail"] == "unreachable"
    loading = app_with(models, mock_client(fail_with=LLMServerError(503))).get("/v1/llm/health", headers=HG)
    assert loading.status_code == 200 and loading.json()["state"] == "degraded"


def test_client_is_closed_on_shutdown(models):
    closed = []

    class Closing(MockProvider):
        async def aclose(self):
            closed.append(True)

    config = LLMConfig(provider="mock")
    with TestClient(create_app(models=models, gateway_key=GW, llm=LLMClient(config, Closing(config)))) as c:
        assert c.get("/v1/llm/health", headers=HG).status_code == 200
    assert closed == [True]


def test_no_prompt_or_reply_in_logs(models, caplog):
    c = app_with(models, mock_client(reply="Reply " + SYNTHETIC_MARKER))
    with caplog.at_level(logging.DEBUG):
        c.post("/v1/llm/generate", json={"prompt": SYNTHETIC_PROMPT}, headers=HG)
        app_with(models, mock_client(fail_with=LLMTimeoutError())).post("/v1/llm/generate", json={"prompt": SYNTHETIC_PROMPT}, headers=HG)
    assert SYNTHETIC_MARKER not in caplog.text and "SYN-0001" not in caplog.text


# ---- independence from screening ----
@pytest.mark.parametrize("payload", [MAM_BASE, SAM_BASE, LOW_BASE])
def test_a_dead_model_server_does_not_change_screening_or_health(models, payload):
    plain = app_with(models)
    config = LLMConfig(provider="ollama", endpoint=dead_url(), max_retries=0, connect_timeout_s=0.2)
    with_llm = app_with(models, LLMClient(config))
    for view_headers in (HG,):
        a = plain.post("/v1/screen", json=payload, headers=view_headers)
        b = with_llm.post("/v1/screen", json=payload, headers=view_headers)
        assert a.status_code == b.status_code == 200 and a.json() == b.json()
    assert with_llm.get("/health").json() == plain.get("/health").json()
    assert with_llm.get("/v1/llm/health", headers=HG).status_code == 503              # the model is down, screening is not
    assert with_llm.post("/v1/llm/generate", json={"prompt": "x"}, headers=HG).json()["code"] == "llm_unreachable"
