"""Real HTTP over loopback against tiny fake servers (synthetic replies only). Covers what MockTransport cannot:
connection refused, slow servers, redirects, proxy variables and the headers that actually reach the wire."""
import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from tests.llm._support import SYNTHETIC_PROMPT, need_httpx, run

need_httpx()

from thanzi_screen.llm import (LLMClient, LLMConfig, LLMConnectionError, LLMResponseError,  # noqa: E402
                               LLMTimeoutError)


class FakeServer:
    """routes: (method, path) -> (status, body dict, delay seconds, extra headers). Records every request."""

    def __init__(self, routes):
        self.routes, self.seen = routes, []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                outer.seen.append({"method": self.command, "path": self.path, "auth": self.headers.get("Authorization"),
                                   "body": json.loads(body) if body else None})
                status, payload, delay, headers = outer.routes.get((self.command, self.path), (404, {}, 0, {}))
                time.sleep(delay)
                data = json.dumps(payload).encode()
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = _serve

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.server.server_address[1]

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()


OLLAMA_CHAT = {"model": "qwen2.5:1.5b", "done": True, "done_reason": "stop", "message": {"role": "assistant", "content": "Synthetic reply."},
               "prompt_eval_count": 5, "eval_count": 3}


def closed_port_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return "http://127.0.0.1:%d" % s.getsockname()[1]


async def one_call(config):
    async with LLMClient(config) as client:
        return await client.generate(SYNTHETIC_PROMPT), await client.health()


def test_ollama_end_to_end():
    routes = {("POST", "/api/chat"): (200, OLLAMA_CHAT, 0, {}),
              ("GET", "/api/tags"): (200, {"models": [{"name": "qwen2.5:1.5b"}]}, 0, {})}
    with FakeServer(routes) as srv:
        result, health = run(one_call(LLMConfig(provider="ollama", endpoint=srv.url)))
    assert result.text == "Synthetic reply." and result.usage.completion_tokens == 3 and health.state == "ok"
    chat = next(r for r in srv.seen if r["path"] == "/api/chat")
    assert chat["body"]["messages"][-1]["content"] == SYNTHETIC_PROMPT and chat["auth"] is None


def test_llamacpp_end_to_end_with_api_key():
    reply = {"choices": [{"message": {"content": "Synthetic reply."}, "finish_reason": "stop"}], "usage": {"completion_tokens": 3}}
    routes = {("POST", "/v1/chat/completions"): (200, reply, 0, {}), ("GET", "/health"): (200, {"status": "ok"}, 0, {})}
    with FakeServer(routes) as srv:
        result, health = run(one_call(LLMConfig(provider="llamacpp", endpoint=srv.url, api_key="k" * 20)))
    assert result.text == "Synthetic reply." and health.state == "ok"
    assert {r["auth"] for r in srv.seen if r["path"] == "/v1/chat/completions"} == {"Bearer " + "k" * 20}


def test_connection_refused_is_retried_once_then_reported():
    config = LLMConfig(provider="ollama", endpoint=closed_port_url(), retry_backoff_s=0.0, max_retries=1)

    async def scenario():
        async with LLMClient(config) as client:
            with pytest.raises(LLMConnectionError):
                await client.generate("x")
            return await client.health()

    status = run(scenario())
    assert (status.state, status.detail) == ("unavailable", "unreachable")


def test_slow_server_times_out_and_is_not_retried():
    routes = {("POST", "/api/chat"): (200, OLLAMA_CHAT, 1.0, {})}
    with FakeServer(routes) as srv:
        config = LLMConfig(provider="ollama", endpoint=srv.url, request_timeout_s=0.2, connect_timeout_s=0.5, max_retries=2)

        async def scenario():
            async with LLMClient(config) as client:
                with pytest.raises(LLMTimeoutError):
                    await client.generate("x")

        run(scenario())
    assert len([r for r in srv.seen if r["path"] == "/api/chat"]) == 1


def test_redirect_is_not_followed():
    routes = {("POST", "/api/chat"): (302, {}, 0, {"Location": "/elsewhere"}), ("POST", "/elsewhere"): (200, OLLAMA_CHAT, 0, {})}
    with FakeServer(routes) as srv:
        async def scenario():
            async with LLMClient(LLMConfig(provider="ollama", endpoint=srv.url)) as client:
                with pytest.raises(LLMResponseError):
                    await client.generate("x")

        run(scenario())
    assert all(r["path"] != "/elsewhere" for r in srv.seen)


def test_proxy_environment_variables_are_ignored(monkeypatch):
    for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(name, closed_port_url())              # a proxy that does not exist: any use would fail
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    routes = {("POST", "/api/chat"): (200, OLLAMA_CHAT, 0, {}), ("GET", "/api/tags"): (200, {"models": []}, 0, {})}
    with FakeServer(routes) as srv:
        result, _ = run(one_call(LLMConfig(provider="ollama", endpoint=srv.url)))
    assert result.text == "Synthetic reply."


def test_path_prefix_in_endpoint_is_kept():
    routes = {("POST", "/ollama/api/chat"): (200, OLLAMA_CHAT, 0, {}), ("GET", "/ollama/api/tags"): (200, {"models": []}, 0, {})}
    with FakeServer(routes) as srv:
        result, health = run(one_call(LLMConfig(provider="ollama", endpoint=srv.url + "/ollama/")))
    assert result.text == "Synthetic reply." and health.detail == "model_not_found"
