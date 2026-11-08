"""Ollama (native API). Good default for small Qwen models: `ollama pull qwen2.5:1.5b`."""
from __future__ import annotations

import re
import time
from typing import Sequence

from ..base import LLMProvider
from ..config import LLMConfig
from ..errors import LLMResponseError
from ..http import JsonHttp
from ..types import Completion, GenerationParams, HealthStatus, Message, Usage


def keep_alive_value(text: str):
    """Ollama takes a duration string ("5m") or a number of seconds. A bare integer is sent as a number."""
    return int(text) if re.fullmatch(r"-?\d+", text) else text


def model_listed(model: str, names: Sequence[str]) -> bool:
    wanted = model if ":" in model else model + ":latest"
    return wanted in names or model in names


def _count(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, config: LLMConfig, http: JsonHttp) -> None:
        super().__init__(config)
        self._http = http

    @classmethod
    def create(cls, config: LLMConfig, transport=None) -> "OllamaProvider":
        return cls(config, JsonHttp(config, transport))

    def build_body(self, messages: Sequence[Message], params: GenerationParams) -> dict:
        options = {"temperature": params.temperature, "top_p": params.top_p, "top_k": params.top_k,
                   "seed": params.seed, "num_predict": params.max_tokens, "num_ctx": params.context_tokens}
        options = {k: v for k, v in options.items() if v is not None}
        if params.stop:
            options["stop"] = list(params.stop)
        body: dict = {"model": self.config.model, "stream": False, "options": options,
                      "messages": [{"role": m.role, "content": m.content} for m in messages]}
        if self.config.keep_alive is not None:
            body["keep_alive"] = keep_alive_value(self.config.keep_alive)
        if self.config.think is not None:
            body["think"] = self.config.think
        return body

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Completion:
        data = await self._http.request_json("POST", "api/chat", self.build_body(messages, params))
        message = data.get("message") if isinstance(data, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or data.get("done") is not True:
            raise LLMResponseError("The reply did not have the expected fields.")
        reason = data.get("done_reason")
        finish = "stop" if reason == "stop" else "length" if reason == "length" else "other"
        usage = Usage(_count(data.get("prompt_eval_count")), _count(data.get("eval_count")))
        model = data.get("model") if isinstance(data.get("model"), str) else None
        return Completion(text, finish, usage, model)

    async def health(self) -> HealthStatus:
        start = time.monotonic()
        data = await self._http.request_json("GET", "api/tags", timeout_s=self.config.health_timeout_s)
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, list):
            raise LLMResponseError("The model list was not in the expected form.")
        names = [m.get("name") for m in models if isinstance(m, dict) and isinstance(m.get("name"), str)]
        present = model_listed(self.config.model, names)
        ms = (time.monotonic() - start) * 1000
        return self.status("ok" if present else "degraded", "ok" if present else "model_not_found", present, ms)

    async def aclose(self) -> None:
        await self._http.aclose()
