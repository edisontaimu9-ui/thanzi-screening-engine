"""In-process provider for development and tests. Makes no network call and needs no model.

It only ever sees what the caller sends, so tests must use synthetic text. The reply is a fixed, labelled string.
"""
from __future__ import annotations

import asyncio
from typing import Sequence

from ..base import LLMProvider
from ..config import LLMConfig
from ..errors import LLMError
from ..types import Completion, GenerationParams, HealthStatus, Message, Usage

MOCK_REPLY = "[mock model] Synthetic reply. No language model was run."


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(self, config: LLMConfig, reply: str = MOCK_REPLY, delay_s: float = 0.0,
                 fail_with: LLMError | None = None) -> None:
        super().__init__(config)
        self.reply, self.delay_s, self.fail_with = reply, delay_s, fail_with
        self.calls: list[tuple[tuple[Message, ...], GenerationParams]] = []     # for assertions in tests

    async def generate(self, messages: Sequence[Message], params: GenerationParams) -> Completion:
        self.calls.append((tuple(messages), params))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if self.fail_with is not None:
            raise self.fail_with
        return Completion(self.reply, "stop", Usage(sum(len(m.content) for m in messages) // 4, len(self.reply) // 4),
                          self.config.model)

    async def health(self) -> HealthStatus:
        if self.fail_with is not None:
            raise self.fail_with
        return self.status("ok", "ok", True, 0.0)
