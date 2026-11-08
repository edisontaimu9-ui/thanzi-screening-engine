"""Wire formats, status mapping and health for each provider, against httpx.MockTransport (no network)."""
import json

import pytest

from tests.llm._support import SYNTHETIC_PROMPT, need_httpx, run

need_httpx()

import httpx  # noqa: E402

from thanzi_screen.llm import (GenerationParams, LLMAuthError, LLMConfig, LLMConfigError, LLMConnectionError,  # noqa: E402
                               LLMModelNotFoundError, LLMRejectedError, LLMResponseError, LLMServerError,
                               LLMTimeoutError, Message, build_provider, register_provider)
from thanzi_screen.llm.providers import PROVIDERS, MockProvider  # noqa: E402

MSGS = [Message("system", "Be brief."), Message("user", SYNTHETIC_PROMPT)]


def provider(name, handler, **cfg):
    config = LLMConfig(provider=name, model=cfg.pop("model", "qwen2.5:1.5b"), **cfg)
    return build_provider(config, transport=httpx.MockTransport(handler))


def ollama_ok(request):
    return httpx.Response(200, json={"model": "qwen2.5:1.5b", "done": True, "done_reason": "stop",
                                     "message": {"role": "assistant", "content": "Fine."},
                                     "prompt_eval_count": 12, "eval_count": 3})


# ---- Ollama ----
def test_ollama_request_shape():
    seen = {}

    def handler(request):
        seen.update(path=request.url.path, body=json.loads(request.content), auth=request.headers.get("authorization"))
        return ollama_ok(request)

    p = provider("ollama", handler, keep_alive="0", think=False)
    params = GenerationParams(max_tokens=64, temperature=0.0, top_p=0.9, top_k=20, seed=7, stop=("###",), context_tokens=1024)
    out = run(p.generate(MSGS, params))
    assert seen["path"] == "/api/chat" and seen["auth"] is None
    body = seen["body"]
    assert body["stream"] is False and body["model"] == "qwen2.5:1.5b" and body["keep_alive"] == 0 and body["think"] is False
    assert body["options"] == {"temperature": 0.0, "top_p": 0.9, "top_k": 20, "seed": 7, "num_predict": 64,
                               "num_ctx": 1024, "stop": ["###"]}
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert (out.text, out.finish_reason, out.usage.prompt_tokens, out.usage.completion_tokens) == ("Fine.", "stop", 12, 3)


def test_ollama_omits_unset_options_and_think():
    seen = {}
    p = provider("ollama", lambda r: (seen.update(body=json.loads(r.content)), ollama_ok(r))[1], keep_alive=None)
    run(p.generate(MSGS, GenerationParams(max_tokens=None, temperature=None, context_tokens=None)))
    assert seen["body"]["options"] == {} and "think" not in seen["body"] and "keep_alive" not in seen["body"]


@pytest.mark.parametrize("reason,expected", [("stop", "stop"), ("length", "length"), ("load", "other"), (None, "other")])
def test_ollama_finish_reasons(reason, expected):
    p = provider("ollama", lambda r: httpx.Response(200, json={"done": True, "done_reason": reason,
                                                                "message": {"content": "x"}}))
    assert run(p.generate(MSGS, GenerationParams())).finish_reason == expected


@pytest.mark.parametrize("payload", [{"done": False, "message": {"content": "x"}}, {"done": True}, {"done": True, "message": {"content": 5}},
                                     {"done": True, "message": "text"}])
def test_ollama_bad_payloads(payload):
    with pytest.raises(LLMResponseError):
        run(provider("ollama", lambda r: httpx.Response(200, json=payload)).generate(MSGS, GenerationParams()))


def test_ollama_health_states():
    def tags(models):
        return lambda r: httpx.Response(200, json={"models": [{"name": n} for n in models]})
    ok = run(provider("ollama", tags(["qwen2.5:1.5b", "other:1b"])).health())
    assert (ok.state, ok.detail, ok.model_available) == ("ok", "ok", True) and ok.latency_ms is not None
    missing = run(provider("ollama", tags(["other:1b"])).health())
    assert (missing.state, missing.detail, missing.model_available) == ("degraded", "model_not_found", False)
    with pytest.raises(LLMResponseError):
        run(provider("ollama", lambda r: httpx.Response(200, json={"nope": 1})).health())


# ---- OpenAI-compatible and llama.cpp ----
def chat_ok(request):
    return httpx.Response(200, json={"model": "m", "choices": [{"message": {"role": "assistant", "content": "Hi."},
                                                                "finish_reason": "length"}],
                                     "usage": {"prompt_tokens": 9, "completion_tokens": 2}})


@pytest.mark.parametrize("name", ["openai_compat", "llamacpp"])
def test_openai_style_request_and_reply(name):
    seen = {}

    def handler(request):
        seen.update(path=request.url.path, body=json.loads(request.content), auth=request.headers.get("authorization"))
        return chat_ok(request)

    p = provider(name, handler, endpoint="http://127.0.0.1:8080", api_key="k" * 20)
    out = run(p.generate(MSGS, GenerationParams(max_tokens=32, temperature=0.3, seed=1, stop=("x",))))
    assert seen["path"] == "/v1/chat/completions" and seen["auth"] == "Bearer " + "k" * 20
    body = seen["body"]
    assert body["stream"] is False and body["max_tokens"] == 32 and body["temperature"] == 0.3 and body["stop"] == ["x"]
    assert "top_k" not in body and "num_ctx" not in json.dumps(body)       # only sent when set; context is a server setting
    assert (out.text, out.finish_reason, out.usage.completion_tokens) == ("Hi.", "length", 2)


def test_openai_top_k_sent_when_set():
    seen = {}
    p = provider("llamacpp", lambda r: (seen.update(body=json.loads(r.content)), chat_ok(r))[1])
    run(p.generate(MSGS, GenerationParams(top_k=40)))
    assert seen["body"]["top_k"] == 40


@pytest.mark.parametrize("payload", [{}, {"choices": []}, {"choices": [{"message": {}}]}, {"choices": [{"message": {"content": None}}]}])
def test_openai_bad_payloads(payload):
    with pytest.raises(LLMResponseError):
        run(provider("openai_compat", lambda r: httpx.Response(200, json=payload)).generate(MSGS, GenerationParams()))


def test_openai_compat_health_checks_model_list():
    def models(ids):
        return lambda r: httpx.Response(200, json={"data": [{"id": i} for i in ids]})
    assert run(provider("openai_compat", models(["qwen2.5:1.5b"])).health()).state == "ok"
    miss = run(provider("openai_compat", models(["x"])).health())
    assert (miss.state, miss.detail) == ("degraded", "model_not_found")


def test_llamacpp_health_ok_loading_and_error():
    ok = run(provider("llamacpp", lambda r: httpx.Response(200, json={"status": "ok"})).health())
    assert (ok.state, ok.model_available) == ("ok", None)
    loading = run(provider("llamacpp", lambda r: httpx.Response(503, json={"error": {"message": "Loading model"}})).health())
    assert (loading.state, loading.detail) == ("degraded", "loading")
    with pytest.raises(LLMServerError):
        run(provider("llamacpp", lambda r: httpx.Response(500, json={})).health())


# ---- transport behaviour shared by the network providers ----
@pytest.mark.parametrize("status,error,retryable", [
    (401, LLMAuthError, False), (403, LLMAuthError, False), (404, LLMModelNotFoundError, False),
    (429, LLMServerError, True), (500, LLMServerError, False), (502, LLMServerError, True),
    (503, LLMServerError, True), (504, LLMServerError, True), (400, LLMRejectedError, False),
    (422, LLMRejectedError, False), (302, LLMResponseError, False)])
def test_status_mapping(status, error, retryable):
    with pytest.raises(error) as e:
        run(provider("ollama", lambda r: httpx.Response(status, json={"error": "SECRET-DETAIL " + SYNTHETIC_PROMPT})).generate(MSGS, GenerationParams()))
    assert e.value.retryable is retryable
    assert "SECRET-DETAIL" not in str(e.value) and "SYN-0001" not in str(e.value)      # server text is never copied


def test_redirects_are_not_followed():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://elsewhere.example/api/chat"})

    with pytest.raises(LLMResponseError):
        run(provider("ollama", handler).generate(MSGS, GenerationParams()))
    assert calls == ["http://127.0.0.1:11434/api/chat"]


@pytest.mark.parametrize("exc,error", [(httpx.ConnectError("x"), LLMConnectionError), (httpx.ReadTimeout("x"), LLMTimeoutError),
                                       (httpx.ConnectTimeout("x"), LLMTimeoutError), (httpx.RemoteProtocolError("x"), LLMConnectionError)])
def test_transport_failures(exc, error):
    def handler(request):
        raise exc
    with pytest.raises(error):
        run(provider("ollama", handler).generate(MSGS, GenerationParams()))


@pytest.mark.parametrize("content", [b"not json", b"", b"\xff\xfe", b"123", b'"text"'])
def test_non_json_or_non_object_reply(content):
    with pytest.raises(LLMResponseError):
        run(provider("ollama", lambda r: httpx.Response(200, content=content)).generate(MSGS, GenerationParams()))


def test_reply_size_cap_by_header_and_by_stream():
    with pytest.raises(LLMResponseError):
        run(provider("ollama", lambda r: httpx.Response(200, content=b"x" * 5000), max_response_bytes=1000).generate(MSGS, GenerationParams()))

    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(10):
                yield b"x" * 400

    with pytest.raises(LLMResponseError):                                    # no content-length: caught while reading
        run(provider("ollama", lambda r: httpx.Response(200, stream=Chunks()), max_response_bytes=1000).generate(MSGS, GenerationParams()))


# ---- registry ----
def test_registry_known_unknown_and_custom():
    assert {"ollama", "llamacpp", "openai_compat", "mock"} <= set(PROVIDERS)
    with pytest.raises(LLMConfigError):
        build_provider(LLMConfig(provider="nope"))
    with pytest.raises(LLMConfigError):
        register_provider("ollama", MockProvider)                            # no silent replacement
    register_provider("custom_test", MockProvider)
    try:
        assert build_provider(LLMConfig(provider="custom_test")).name == "mock"
    finally:
        PROVIDERS.pop("custom_test")


def test_mock_provider_is_deterministic_and_offline():
    p = build_provider(LLMConfig(provider="mock"))
    out = run(p.generate(MSGS, GenerationParams()))
    assert out.text.startswith("[mock model]") and run(p.health()).state == "ok" and len(p.calls) == 1
