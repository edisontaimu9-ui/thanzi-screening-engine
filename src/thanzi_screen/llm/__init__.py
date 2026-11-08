"""Local LLM client for Thanzi AI. Provider-agnostic, async, standard library plus httpx (extra `llm`).

Independence rule (D128): nothing in this package imports the screening code, and the screening code never imports
this package. A model's text is never an input to classification, referral or any clinical rule.
"""
from .base import LLMProvider, TextGenerator
from .client import LLMClient, build_client
from .config import LLMConfig, check_endpoint, enabled_from_env, is_local_host
from .errors import (LLMAuthError, LLMBadRequestError, LLMBusyError, LLMConfigError, LLMConnectionError, LLMError,
                     LLMModelNotFoundError, LLMRejectedError, LLMResponseError, LLMServerError, LLMTimeoutError)
from .providers import PROVIDERS, build_provider, register_provider
from .text import strip_reasoning
from .types import Completion, GenerationParams, GenerationResult, HealthStatus, Message, Usage

__all__ = [
    "LLMClient", "LLMConfig", "LLMProvider", "TextGenerator", "build_client", "build_provider", "register_provider",
    "PROVIDERS", "check_endpoint", "enabled_from_env", "is_local_host", "strip_reasoning",
    "Completion", "GenerationParams", "GenerationResult", "HealthStatus", "Message", "Usage",
    "LLMError", "LLMConfigError", "LLMBadRequestError", "LLMBusyError", "LLMConnectionError", "LLMTimeoutError",
    "LLMAuthError", "LLMModelNotFoundError", "LLMServerError", "LLMRejectedError", "LLMResponseError",
]
