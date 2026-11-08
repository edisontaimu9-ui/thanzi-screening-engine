"""Client behaviour: limits, retries, deadlines, clean-up, health and log privacy. Mock provider, no network."""
import asyncio
import logging

import pytest

from tests.llm._support import SYNTHETIC_MARKER, SYNTHETIC_PROMPT, run
from thanzi_screen.llm import (GenerationParams, LLMBadRequestError, LLMBusyError, LLMClient, LLMConfig, LLMConnectionError,
                               LLMError, LLMResponseError, LLMServerError, LLMTimeoutError, Message, TextGenerator,
                               LLMAuthError)
from thanzi_screen.llm.providers import MockProvider
from thanzi_screen.llm.types import Completion

FAST = dict(provider="mock", retry_backoff_s=0.0)


def make(provider_kwargs=None, **cfg):
    config = LLMConfig(**{**FAST, **cfg})
    provider = MockProvider(config, **(provider_kwargs or {}))
    return LLMClient(config, provider), provider


class Sequence(MockProvider):
    """Raises the given errors in turn, then succeeds."""
    def __init__(self, config, errors):
        super().__init__(config)
        self.errors = list(errors)

    async def generate(self, messages, params):
        self.calls.append((tuple(messages), params))
        if self.errors:
            raise self.errors.pop(0)
        return Completion("ok", "stop")


def test_generate_builds_messages_and_uses_default_params():
    client, provider = make()
    result = run(client.generate(SYNTHETIC_PROMPT, system="Be brief."))
    messages, params = provider.calls[0]
    assert [m.role for m in messages] == ["system", "user"] and messages[1].content == SYNTHETIC_PROMPT
    assert params == client.config.params
    assert (result.provider, result.model, result.finish_reason) == ("mock", "qwen2.5:1.5b", "stop") and result.latency_ms >= 0


def test_message_list_and_param_override():
    client, provider = make()
    run(client.generate([Message("user", "a"), Message("assistant", "b"), Message("user", "c")],
                        params=GenerationParams(max_tokens=16)))
    assert len(provider.calls[0][0]) == 3 and provider.calls[0][1].max_tokens == 16


def test_reasoning_is_stripped_unless_disabled():
    raw = "<think>private reasoning</think>Visible."
    client, _ = make({"reply": raw})
    assert run(client.generate("x")).text == "Visible."
    client, _ = make({"reply": raw}, strip_reasoning=False)
    assert run(client.generate("x")).text == raw


def test_prompt_limit_and_empty_input_rejected_before_the_provider():
    client, provider = make(max_prompt_chars=50)
    for bad in ("x" * 51, []):
        with pytest.raises(LLMBadRequestError):
            run(client.generate(bad))
    assert provider.calls == []


def test_retry_on_transient_error_then_success_with_backoff():
    config = LLMConfig(provider="mock", max_retries=2, retry_backoff_s=1.0)
    provider = Sequence(config, [LLMConnectionError(), LLMServerError(503)])
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    client = LLMClient(config, provider, sleep=fake_sleep, jitter=lambda: 0.5)
    assert run(client.generate("x")).text == "ok" and len(provider.calls) == 3
    assert slept == [1.0, 2.0]                                   # exponential, jitter fixed for the test


@pytest.mark.parametrize("error", [LLMTimeoutError(), LLMServerError(500), LLMAuthError(), LLMResponseError()])
def test_no_retry_for_timeouts_oom_auth_or_bad_replies(error):
    config = LLMConfig(**FAST, max_retries=3)
    provider = Sequence(config, [error, error, error])
    with pytest.raises(type(error)):
        run(LLMClient(config, provider).generate("x"))
    assert len(provider.calls) == 1


def test_retries_are_limited():
    config = LLMConfig(**FAST, max_retries=1)
    provider = Sequence(config, [LLMConnectionError()] * 5)
    with pytest.raises(LLMConnectionError):
        run(LLMClient(config, provider).generate("x"))
    assert len(provider.calls) == 2


def test_overall_deadline_raises_timeout():
    client, _ = make({"delay_s": 0.5}, connect_timeout_s=0.05, request_timeout_s=0.1)
    with pytest.raises(LLMTimeoutError):
        run(client.generate("x"))


def test_one_at_a_time_by_default_and_busy_when_queue_wait_runs_out():
    async def scenario(queue_timeout):
        client, provider = make({"delay_s": 0.15}, queue_timeout_s=queue_timeout)
        return await asyncio.gather(client.generate("a"), client.generate("b"), return_exceptions=True)

    first, second = run(scenario(0.05))
    assert not isinstance(first, Exception) and isinstance(second, LLMBusyError)
    results = run(scenario(2.0))                                 # patient queue: both succeed, one after the other
    assert all(not isinstance(r, Exception) for r in results)


def test_slot_is_released_after_a_failure():
    async def scenario():
        client, provider = make(queue_timeout_s=0.05)
        provider.fail_with = LLMTimeoutError()
        with pytest.raises(LLMTimeoutError):
            await client.generate("x")
        provider.fail_with = None
        return await client.generate("y")

    assert run(scenario()).text.startswith("[mock model]")


def test_two_slots_run_in_parallel():
    async def scenario():
        client, _ = make({"delay_s": 0.2}, max_concurrency=2, queue_timeout_s=0.05)
        loop = asyncio.get_running_loop()
        start = loop.time()
        await asyncio.gather(client.generate("a"), client.generate("b"))
        return loop.time() - start

    assert run(scenario()) < 0.38


def test_provider_bug_becomes_a_generic_error_without_details(caplog):
    class Broken(MockProvider):
        async def generate(self, messages, params):
            raise RuntimeError("contains " + SYNTHETIC_MARKER)

    config = LLMConfig(**FAST)
    with caplog.at_level(logging.DEBUG, logger="thanzi.llm"), pytest.raises(LLMError) as e:
        run(LLMClient(config, Broken(config)).generate("x"))
    assert type(e.value) is LLMError and SYNTHETIC_MARKER not in str(e.value)
    assert SYNTHETIC_MARKER not in caplog.text and "RuntimeError" in caplog.text


# ---- health ----
@pytest.mark.parametrize("error,state,detail", [
    (LLMConnectionError(), "unavailable", "unreachable"), (LLMTimeoutError(), "unavailable", "timeout"),
    (LLMAuthError(), "unavailable", "unauthorised"), (LLMServerError(503), "degraded", "loading"),
    (LLMServerError(500), "unavailable", "error"), (LLMResponseError(), "unavailable", "bad_response"),
    (RuntimeError("boom"), "unavailable", "error")])
def test_health_never_raises(error, state, detail):
    client, provider = make()
    provider.fail_with = error
    status = run(client.health())
    assert (status.state, status.detail) == (state, detail) and status.provider == "mock"


def test_health_ok_and_dict_shape():
    status = run(make()[0].health())
    assert status.as_dict() == {"state": "ok", "provider": "mock", "model": "qwen2.5:1.5b", "detail": "ok",
                                "model_available": True, "latency_ms": 0.0}


def test_health_times_out_without_raising():
    class Slow(MockProvider):
        async def health(self):
            await asyncio.sleep(1)

    config = LLMConfig(**FAST, connect_timeout_s=0.05, health_timeout_s=0.05)
    assert run(LLMClient(config, Slow(config)).health()).detail == "timeout"


def test_health_does_not_wait_for_a_busy_slot():
    async def scenario():
        client, _ = make({"delay_s": 0.3})
        busy = asyncio.create_task(client.generate("x"))
        await asyncio.sleep(0.05)
        loop = asyncio.get_running_loop()
        start = loop.time()
        status = await client.health()
        took = loop.time() - start
        await busy
        return status, took

    status, took = run(scenario())
    assert status.state == "ok" and took < 0.2


# ---- privacy and lifecycle ----
def test_logs_hold_metadata_only(caplog):
    client, _ = make({"reply": "Reply mentions " + SYNTHETIC_MARKER})
    with caplog.at_level(logging.DEBUG, logger="thanzi.llm"):
        run(client.generate(SYNTHETIC_PROMPT, system="System " + SYNTHETIC_MARKER))
        provider = client.provider
        provider.fail_with = LLMConnectionError()
        with pytest.raises(LLMConnectionError):
            run(client.generate(SYNTHETIC_PROMPT))
    assert caplog.text and SYNTHETIC_MARKER not in caplog.text and "SYN-" not in caplog.text
    assert "provider=mock" in caplog.text and "code=llm_unreachable" in caplog.text


def test_client_satisfies_the_text_generator_protocol_and_closes():
    closed = []

    class Closing(MockProvider):
        async def aclose(self):
            closed.append(True)

    async def scenario():
        config = LLMConfig(**FAST)
        async with LLMClient(config, Closing(config)) as client:
            assert isinstance(client, TextGenerator)
            await client.generate("x")

    run(scenario())
    assert closed == [True]
