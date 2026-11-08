"""The two seams of the package: the provider contract and the small interface that callers depend on."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, Sequence, runtime_checkable

from .config import LLMConfig
from .errors import (LLMAuthError, LLMConnectionError, LLMError, LLMServerError, LLMTimeoutError)
from .types import Completion, GenerationParams, GenerationResult, HealthStatus, Message


@runtime_checkable
class TextGenerator(Protocol):
    """What any other part of the system should depend on, so the model, the server or the whole provider can be
    replaced without touching the caller. `LLMClient` implements it."""

    async def generate(self, prompt: "str | Sequence[Message]", *, system: str | None = None,
                       params: GenerationParams | None = None) -> GenerationResult: ...

    async def health(self) -> HealthStatus: ...

    async def aclose(self) -> None: ...


class LLMProvider(ABC):
    """One model server. Providers translate to and from the server's wire format and nothing else: timeouts
    around the whole call, retries, concurrency limits and output clean-up belong to `LLMClient`."""
    name: str = ""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    @classmethod
    def create(cls, config: LLMConfig, transport=None) -> "LLMProvider":
        return cls(config)

    @abstractmethod
    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Completion: ...

    @abstractmethod
    async def health(self) -> HealthStatus:
        """May raise LLMError. `LLMClient.health()` turns any failure into a status."""

    async def aclose(self) -> None:
        return None

    # ---- helpers for subclasses ----
    def status(self, state, detail="ok", model_available=None, latency_ms=None) -> HealthStatus:
        return HealthStatus(state, self.name, self.config.model, detail, model_available, latency_ms)


def status_from_error(provider: str, model: str, exc: BaseException, latency_ms: float | None = None) -> HealthStatus:
    """Map a failure to a health status. Used by the client, so health checks never raise."""
    detail, state = "error", "unavailable"
    if isinstance(exc, LLMTimeoutError):
        detail = "timeout"
    elif isinstance(exc, LLMConnectionError):
        detail = "unreachable"
    elif isinstance(exc, LLMAuthError):
        detail = "unauthorised"
    elif isinstance(exc, LLMServerError) and exc.status_code == 503:
        detail, state = "loading", "degraded"                   # reachable but not ready (llama.cpp while loading)
    elif isinstance(exc, LLMError) and exc.code == "llm_bad_response":
        detail = "bad_response"
    return HealthStatus(state, provider, model, detail, None, latency_ms)
