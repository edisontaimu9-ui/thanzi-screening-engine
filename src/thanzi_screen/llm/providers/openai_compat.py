"""OpenAI-compatible chat servers (`/v1/chat/completions`): llama.cpp `llama-server`, llama-cpp-python, vLLM,
LM Studio and others. `LlamaCppProvider` adds llama.cpp's own `/health` check."""
from __future__ import annotations

import time
from typing import Sequence

from ..base import LLMProvider
from ..config import LLMConfig
from ..errors import LLMResponseError, LLMServerError
from ..http import JsonHttp
from ..types import Completion, GenerationParams, HealthStatus, Message, Usage


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"

    def __init__(self, config: LLMConfig, http: JsonHttp) -> None:
        super().__init__(config)
        self._http = http

    @classmethod
    def create(cls, config: LLMConfig, transport=None):
        return cls(config, JsonHttp(config, transport))

    def build_body(self, messages: Sequence[Message], params: GenerationParams) -> dict:
        body: dict = {"model": self.config.model, "stream": False,
                      "messages": [{"role": m.role, "content": m.content} for m in messages]}
        for key, value in (("max_tokens", params.max_tokens), ("temperature", params.temperature),
                           ("top_p", params.top_p), ("seed", params.seed),
                           ("top_k", params.top_k)):              # top_k is an extension that llama.cpp and vLLM accept
            if value is not None:
                body[key] = value
        if params.stop:
            body["stop"] = list(params.stop)
        return body

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Completion:
        data = await self._http.request_json("POST", "v1/chat/completions", self.build_body(messages, params))
        try:
            choice = data["choices"][0]
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LLMResponseError("The reply did not have the expected fields.") from None
        if not isinstance(text, str):
            raise LLMResponseError("The reply did not have the expected fields.")
        reason = choice.get("finish_reason")
        finish = "stop" if reason == "stop" else "length" if reason == "length" else "other"
        raw = data.get("usage")
        usage = Usage(_count(raw.get("prompt_tokens")), _count(raw.get("completion_tokens"))) \
            if isinstance(raw, dict) else None
        model = data.get("model") if isinstance(data.get("model"), str) else None
        return Completion(text, finish, usage, model)

    async def health(self) -> HealthStatus:
        start = time.monotonic()
        data = await self._http.request_json("GET", "v1/models", timeout_s=self.config.health_timeout_s)
        entries = data.get("data") if isinstance(data, dict) else None
        if not isinstance(entries, list):
            raise LLMResponseError("The model list was not in the expected form.")
        ids = [e.get("id") for e in entries if isinstance(e, dict) and isinstance(e.get("id"), str)]
        present = self.config.model in ids
        ms = (time.monotonic() - start) * 1000
        return self.status("ok" if present else "degraded", "ok" if present else "model_not_found", present, ms)

    async def aclose(self) -> None:
        await self._http.aclose()


class LlamaCppProvider(OpenAICompatProvider):
    """llama.cpp `llama-server` serves one model, loaded at start-up. The model name in a request is ignored, so
    availability is not checked by name (`model_available` is None). `/health` answers 503 while loading."""
    name = "llamacpp"

    async def health(self) -> HealthStatus:
        start = time.monotonic()
        try:
            data = await self._http.request_json("GET", "health", timeout_s=self.config.health_timeout_s)
        except LLMServerError as exc:
            if exc.status_code == 503:
                return self.status("degraded", "loading", None, (time.monotonic() - start) * 1000)
            raise
        if isinstance(data, dict) and data.get("status") not in (None, "ok"):
            return self.status("degraded", "loading", None, (time.monotonic() - start) * 1000)
        return self.status("ok", "ok", None, (time.monotonic() - start) * 1000)
