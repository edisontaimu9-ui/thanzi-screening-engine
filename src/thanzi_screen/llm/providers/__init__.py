"""Provider registry. To add a server: subclass `LLMProvider`, then `register_provider("name", YourClass)`.
The screening engine never changes: only the `THANZI_LLM_PROVIDER` setting does."""
from __future__ import annotations

from ..base import LLMProvider
from ..config import LLMConfig
from ..errors import LLMConfigError
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai_compat import LlamaCppProvider, OpenAICompatProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "llamacpp": LlamaCppProvider,
    "openai_compat": OpenAICompatProvider,
    "mock": MockProvider,
}


def register_provider(name: str, cls: type[LLMProvider], replace: bool = False) -> None:
    if name in PROVIDERS and not replace:
        raise LLMConfigError("A provider with that name is already registered.")
    PROVIDERS[name] = cls


def build_provider(config: LLMConfig, transport=None) -> LLMProvider:
    try:
        cls = PROVIDERS[config.provider]
    except KeyError:
        raise LLMConfigError("Unknown provider. Known: " + ", ".join(sorted(PROVIDERS))) from None
    return cls.create(config, transport)


__all__ = ["PROVIDERS", "register_provider", "build_provider", "MockProvider", "OllamaProvider",
           "LlamaCppProvider", "OpenAICompatProvider"]
