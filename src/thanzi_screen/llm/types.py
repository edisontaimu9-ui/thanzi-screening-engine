"""Plain data types shared by every provider. Standard library only."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Literal

from .errors import LLMBadRequestError, LLMConfigError

Role = Literal["system", "user", "assistant"]
FinishReason = Literal["stop", "length", "other"]
HealthState = Literal["ok", "degraded", "unavailable"]

MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}")


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ("system", "user", "assistant"):
            raise LLMBadRequestError("Unknown message role.")
        if not isinstance(self.content, str) or not self.content.strip():
            raise LLMBadRequestError("A message must have text.")


@dataclass(frozen=True, slots=True)
class GenerationParams:
    """Sampling and length settings. None means: leave it to the server's default.

    Low-resource defaults: short answers (256 tokens), a small context window (2048) and a low temperature.
    `context_tokens` is honoured by Ollama only. A llama.cpp server fixes its context at start-up (`-c`).
    """
    max_tokens: int | None = 256
    temperature: float | None = 0.2
    top_p: float | None = None
    top_k: int | None = None
    seed: int | None = None
    stop: tuple[str, ...] = ()
    context_tokens: int | None = 2048

    def __post_init__(self) -> None:
        def bad(name: str) -> LLMConfigError:
            return LLMConfigError(f"Generation setting '{name}' is out of range.")
        if self.max_tokens is not None and not 1 <= self.max_tokens <= 8192:
            raise bad("max_tokens")
        if self.temperature is not None and not 0.0 <= self.temperature <= 2.0:
            raise bad("temperature")
        if self.top_p is not None and not 0.0 < self.top_p <= 1.0:
            raise bad("top_p")
        if self.top_k is not None and not 1 <= self.top_k <= 1000:
            raise bad("top_k")
        if self.seed is not None and not 0 <= self.seed <= 2**31 - 1:
            raise bad("seed")
        if self.context_tokens is not None and not 256 <= self.context_tokens <= 32768:
            raise bad("context_tokens")
        if len(self.stop) > 4 or any((not isinstance(s, str)) or not 0 < len(s) <= 64 for s in self.stop):
            raise bad("stop")

    def with_overrides(self, **overrides) -> "GenerationParams":
        """A copy with the given settings replaced. Values that are None are ignored (keep the default)."""
        return replace(self, **{k: v for k, v in overrides.items() if v is not None})


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    """What a provider returns. The client adds timing and cleaning."""
    text: str
    finish_reason: FinishReason = "stop"
    usage: Usage | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class GenerationResult:
    text: str
    model: str
    provider: str
    finish_reason: FinishReason
    latency_ms: float
    usage: Usage | None = None


@dataclass(frozen=True, slots=True)
class HealthStatus:
    """`detail` is a stable code: ok, model_not_found, loading, unreachable, timeout, unauthorised, bad_response, error."""
    state: HealthState
    provider: str
    model: str
    detail: str = "ok"
    model_available: bool | None = None       # None: the server cannot say (single-model llama.cpp)
    latency_ms: float | None = None

    def as_dict(self) -> dict:
        return {"state": self.state, "provider": self.provider, "model": self.model, "detail": self.detail,
                "model_available": self.model_available,
                "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1)}
