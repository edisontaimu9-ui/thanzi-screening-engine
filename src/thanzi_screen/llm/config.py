"""Configuration for the local LLM client. Standard library only.

Everything comes from arguments or `THANZI_LLM_*` environment variables. The API key is never shown in a repr and
never logged. The endpoint must be a local or private address unless `allow_remote` is set on purpose (privacy).
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field, fields
from typing import Mapping
from urllib.parse import urlsplit

from .errors import LLMConfigError
from .types import MODEL_NAME, GenerationParams

ENV_PREFIX = "THANZI_LLM_"
ENV_ENABLED = "THANZI_LLM_ENABLED"
_LOCAL_SUFFIXES = (".internal", ".local", ".lan", ".localdomain", ".svc", ".cluster.local")
_KEEP_ALIVE = re.compile(r"-?\d+|-?\d+(\.\d+)?(ms|s|m|h)")
_PROVIDER_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")


def is_local_host(host: str) -> bool:
    """True for loopback, private and link-local addresses, `localhost`, single-label names (a Docker or
    Kubernetes service name such as `ollama`) and the usual private suffixes. Anything else counts as remote."""
    host = host.strip("[]").lower().rstrip(".")
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    return "." not in host or host.endswith(_LOCAL_SUFFIXES)


def check_endpoint(endpoint: str, allow_remote: bool = False) -> str:
    """Validate the base URL and return it without a trailing slash. Raises LLMConfigError (never echoes the URL)."""
    try:
        parts = urlsplit(endpoint.strip())
        host, _ = parts.hostname, parts.port           # `.port` raises ValueError on a bad port
    except (ValueError, AttributeError):
        raise LLMConfigError("The endpoint is not a valid URL.") from None
    if parts.scheme not in ("http", "https") or not host:
        raise LLMConfigError("The endpoint must be an http or https URL with a host.")
    if parts.username is not None or parts.password is not None:
        raise LLMConfigError("The endpoint must not contain credentials. Use the API key setting.")
    if parts.query or parts.fragment:
        raise LLMConfigError("The endpoint must not contain a query or fragment.")
    if not is_local_host(host):
        if not allow_remote:
            raise LLMConfigError("The endpoint is not a local or private address. Patient privacy: set "
                                 "THANZI_LLM_ALLOW_REMOTE=1 only after the data protection review.")
        if parts.scheme != "https":
            raise LLMConfigError("A remote endpoint must use https.")
    return endpoint.strip().rstrip("/")


def _positive(name: str, value: float, upper: float) -> None:
    if not 0 < value <= upper:
        raise LLMConfigError(f"Setting '{name}' is out of range.")


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "ollama"                       # ollama | llamacpp | openai_compat | mock (or a registered name)
    endpoint: str = "http://127.0.0.1:11434"
    model: str = "qwen2.5:1.5b"
    api_key: str | None = field(default=None, repr=False)
    connect_timeout_s: float = 3.0
    request_timeout_s: float = 60.0                # whole generation, including queue-free retries' single attempt
    health_timeout_s: float = 2.0
    queue_timeout_s: float = 5.0                   # how long a request may wait for a free inference slot
    max_concurrency: int = 1                       # one at a time: small machines run out of memory otherwise
    max_retries: int = 1                           # connection errors and 429/502/503/504 only, never timeouts
    retry_backoff_s: float = 0.5
    max_response_bytes: int = 1_048_576
    max_prompt_chars: int = 8_000
    keep_alive: str | None = "5m"                  # Ollama only: how long the model stays in RAM ("0" unloads at once)
    think: bool | None = None                      # Ollama only: False turns off Qwen3-style thinking. None: not sent
    strip_reasoning: bool = True
    allow_remote: bool = False
    params: GenerationParams = field(default_factory=GenerationParams)

    def __post_init__(self) -> None:
        if not _PROVIDER_NAME.fullmatch(self.provider or ""):
            raise LLMConfigError("The provider name is not valid.")
        object.__setattr__(self, "endpoint", check_endpoint(self.endpoint, self.allow_remote))
        if not MODEL_NAME.fullmatch(self.model or ""):
            raise LLMConfigError("The model name is not valid.")
        if self.api_key is not None and (not self.api_key or any(c in self.api_key for c in "\r\n")):
            raise LLMConfigError("The API key is not valid.")
        _positive("connect_timeout_s", self.connect_timeout_s, 60)
        _positive("request_timeout_s", self.request_timeout_s, 900)
        _positive("health_timeout_s", self.health_timeout_s, 60)
        _positive("queue_timeout_s", self.queue_timeout_s, 600)
        _positive("max_response_bytes", self.max_response_bytes, 64 * 1024 * 1024)
        _positive("max_prompt_chars", self.max_prompt_chars, 200_000)
        if not 1 <= self.max_concurrency <= 8:
            raise LLMConfigError("Setting 'max_concurrency' is out of range.")
        if not 0 <= self.max_retries <= 3:
            raise LLMConfigError("Setting 'max_retries' is out of range.")
        if not 0 <= self.retry_backoff_s <= 30:
            raise LLMConfigError("Setting 'retry_backoff_s' is out of range.")
        if self.keep_alive is not None and not _KEEP_ALIVE.fullmatch(self.keep_alive):
            raise LLMConfigError("Setting 'keep_alive' must look like 0, -1, 30s, 5m or 1h.")

    # ---- loading ----
    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "LLMConfig":
        """Build from plain values (a parsed JSON file, for example). Unknown keys are refused."""
        top = {f.name for f in fields(cls)} - {"params"}
        gen = {f.name for f in fields(GenerationParams)}
        unknown = sorted(set(values) - top - gen - {"params"})
        if unknown:
            raise LLMConfigError("Unknown setting: " + ", ".join(unknown))
        try:
            params = dict(values.get("params") or {})                   # type: ignore[arg-type]
            params.update({k: v for k, v in values.items() if k in gen})
            if "stop" in params:
                params["stop"] = tuple(params["stop"] or ())
            return cls(**{k: v for k, v in values.items() if k in top},
                       params=GenerationParams(**params))
        except TypeError:
            raise LLMConfigError("A setting has the wrong type.") from None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "LLMConfig":
        """Read `THANZI_LLM_*` variables. An invalid value names the variable, never its content."""
        import os
        env = os.environ if env is None else env
        values: dict[str, object] = {}

        def put(key: str, name: str, convert) -> None:
            raw = env.get(ENV_PREFIX + name)
            if raw is None or raw == "":
                return
            try:
                values[key] = convert(raw.strip() if key != "api_key" else raw)
            except (ValueError, TypeError):
                raise LLMConfigError(f"{ENV_PREFIX}{name} is not valid.") from None

        for key, name, conv in ENV_SETTINGS:
            put(key, name, conv)
        return cls.from_mapping(values)


def _boolean(raw: str) -> bool:
    if raw.lower() in ("1", "true", "yes", "on"):
        return True
    if raw.lower() in ("0", "false", "no", "off"):
        return False
    raise ValueError


# (setting, variable suffix, converter). The one list that both the loader and the tests read.
ENV_SETTINGS = (
    ("provider", "PROVIDER", str.lower), ("endpoint", "ENDPOINT", str), ("model", "MODEL", str),
    ("api_key", "API_KEY", str), ("connect_timeout_s", "CONNECT_TIMEOUT_S", float),
    ("request_timeout_s", "TIMEOUT_S", float), ("health_timeout_s", "HEALTH_TIMEOUT_S", float),
    ("queue_timeout_s", "QUEUE_TIMEOUT_S", float), ("max_concurrency", "MAX_CONCURRENCY", int),
    ("max_retries", "MAX_RETRIES", int), ("retry_backoff_s", "RETRY_BACKOFF_S", float),
    ("max_response_bytes", "MAX_RESPONSE_BYTES", int), ("max_prompt_chars", "MAX_PROMPT_CHARS", int),
    ("keep_alive", "KEEP_ALIVE", str), ("think", "THINK", _boolean),
    ("strip_reasoning", "STRIP_REASONING", _boolean), ("allow_remote", "ALLOW_REMOTE", _boolean),
    ("max_tokens", "MAX_TOKENS", int), ("temperature", "TEMPERATURE", float), ("top_p", "TOP_P", float),
    ("top_k", "TOP_K", int), ("seed", "SEED", int), ("context_tokens", "CONTEXT_TOKENS", int),
)


def enabled_from_env(env: Mapping[str, str] | None = None) -> bool:
    """The LLM feature is off unless THANZI_LLM_ENABLED=1."""
    import os
    return (os.environ if env is None else env).get(ENV_ENABLED) == "1"
