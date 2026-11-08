"""The async client. Wraps one provider with the behaviour every deployment needs:

- a concurrency limit with a bounded wait (small machines run one inference at a time),
- a hard deadline per attempt and a single, limited retry for transient failures,
- output clean-up (reasoning tags), and
- health checks that never raise.

Logging holds metadata only (provider, model, latency, token counts, error codes). Prompts and replies are never logged.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import replace
from typing import Awaitable, Callable, Mapping, Sequence

from .base import LLMProvider, status_from_error
from .config import LLMConfig
from .errors import LLMBadRequestError, LLMBusyError, LLMError, LLMTimeoutError
from .providers import build_provider
from .text import strip_reasoning
from .types import GenerationParams, GenerationResult, HealthStatus, Message

log = logging.getLogger("thanzi.llm")


class LLMClient:
    def __init__(self, config: LLMConfig, provider: LLMProvider | None = None, *, transport=None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 jitter: Callable[[], float] = random.random) -> None:
        self.config = config
        self.provider = provider if provider is not None else build_provider(config, transport)
        self._slots = asyncio.Semaphore(config.max_concurrency)
        self._sleep, self._jitter = sleep, jitter

    # ---- inference ----
    def _messages(self, prompt: "str | Sequence[Message]", system: str | None) -> list[Message]:
        messages = [Message("user", prompt)] if isinstance(prompt, str) else list(prompt)
        if system:
            messages.insert(0, Message("system", system))
        if not messages:
            raise LLMBadRequestError("There is nothing to send.")
        if sum(len(m.content) for m in messages) > self.config.max_prompt_chars:
            raise LLMBadRequestError("The prompt is longer than the configured limit.")
        return messages

    async def generate(self, prompt: "str | Sequence[Message]", *, system: str | None = None,
                       params: GenerationParams | None = None) -> GenerationResult:
        messages = self._messages(prompt, system)
        params = params or self.config.params
        cfg = self.config
        try:
            async with asyncio.timeout(cfg.queue_timeout_s):
                await self._slots.acquire()
        except TimeoutError:
            log.warning("llm busy provider=%s", self.provider.name)
            raise LLMBusyError() from None
        try:
            start = time.monotonic()
            completion = await self._attempts(messages, params)
        finally:
            self._slots.release()
        latency = (time.monotonic() - start) * 1000
        text = strip_reasoning(completion.text) if cfg.strip_reasoning else completion.text
        result = GenerationResult(text, completion.model or cfg.model, self.provider.name, completion.finish_reason,
                                  latency, completion.usage)
        log.info("llm ok provider=%s model=%s latency_ms=%d finish=%s completion_tokens=%s", result.provider,
                 result.model, latency, result.finish_reason,
                 None if result.usage is None else result.usage.completion_tokens)
        return result

    async def _attempts(self, messages, params):
        cfg = self.config
        for attempt in range(cfg.max_retries + 1):
            try:
                async with asyncio.timeout(cfg.connect_timeout_s + cfg.request_timeout_s):
                    return await self.provider.generate(messages, params)
            except TimeoutError:                                  # the overall deadline: never retried
                log.warning("llm failed provider=%s code=llm_timeout", self.provider.name)
                raise LLMTimeoutError() from None
            except LLMError as exc:
                if exc.retryable and attempt < cfg.max_retries:
                    delay = cfg.retry_backoff_s * (2 ** attempt) * (0.5 + self._jitter())
                    log.warning("llm retry provider=%s code=%s attempt=%d", self.provider.name, exc.code, attempt + 1)
                    await self._sleep(delay)
                    continue
                log.warning("llm failed provider=%s code=%s", self.provider.name, exc.code)
                raise
            except Exception as exc:                              # a provider bug: say the type only
                log.error("llm provider error: %s", type(exc).__name__)
                raise LLMError() from None
        raise LLMError()                                          # not reachable; keeps the type checker honest

    # ---- health ----
    async def health(self) -> HealthStatus:
        """Never raises and does not wait for an inference slot, so a busy model still answers."""
        cfg = self.config
        start = time.monotonic()
        try:
            async with asyncio.timeout(cfg.connect_timeout_s + cfg.health_timeout_s):
                return await self.provider.health()
        except TimeoutError:
            exc: BaseException = LLMTimeoutError()
        except LLMError as err:
            exc = err
        except Exception as err:
            log.error("llm health error: %s", type(err).__name__)
            exc = err
        return status_from_error(self.provider.name, cfg.model, exc, (time.monotonic() - start) * 1000)

    async def aclose(self) -> None:
        await self.provider.aclose()

    async def __aenter__(self) -> "LLMClient":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.aclose()


def build_client(config: LLMConfig | None = None, *, env: Mapping[str, str] | None = None,
                 transport=None) -> LLMClient:
    """Build from a config, or from `THANZI_LLM_*` variables when none is given."""
    return LLMClient(config or LLMConfig.from_env(env), transport=transport)
