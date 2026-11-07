"""Access control and HIV scrubbing for the API (D78, D82, D83). Framework-free.

The service fails closed: no gateway key, no start (unless dev mode is set explicitly). Network isolation,
TLS and rate limits are Hope's deployment work and are not enforced here.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import threading
from dataclasses import dataclass

log = logging.getLogger("thanzi.security")

MIN_KEY_LENGTH = 16
GATEWAY_HEADER = "X-Gateway-Key"
AUDIT_HEADER = "X-Audit-Key"
ENV_GATEWAY_KEY = "THANZI_GATEWAY_KEY"
ENV_AUDIT_KEY = "THANZI_AUDIT_KEY"
ENV_DEV_MODE = "THANZI_DEV_MODE"


class ConfigError(RuntimeError):
    """The service is not safely configured. It must not start."""


@dataclass(frozen=True)
class AccessConfig:
    gateway_key: str | None        # None only in dev mode
    audit_key: str | None          # None means the audit view is off
    dev_mode: bool


def build_config(gateway_key: str | None = None, audit_key: str | None = None, dev_mode: bool = False,
                 env: dict | None = None) -> AccessConfig:
    """Keys come from arguments first, then the environment. Raises ConfigError when unsafe."""
    env = os.environ if env is None else env
    gateway_key = gateway_key or env.get(ENV_GATEWAY_KEY) or None
    audit_key = audit_key or env.get(ENV_AUDIT_KEY) or None
    dev = bool(dev_mode) or env.get(ENV_DEV_MODE) == "1"
    if gateway_key is None and not dev:
        raise ConfigError(f"{ENV_GATEWAY_KEY} is required. Refusing to start without it. "
                          f"({ENV_DEV_MODE}=1 is for local development only.)")
    for name, key in ((ENV_GATEWAY_KEY, gateway_key), (ENV_AUDIT_KEY, audit_key)):
        if key is not None and len(key) < MIN_KEY_LENGTH:
            raise ConfigError(f"{name} must be at least {MIN_KEY_LENGTH} characters.")
    if gateway_key is not None and gateway_key == audit_key:
        raise ConfigError("The audit key must differ from the gateway key.")
    if dev:
        log.warning("DEV MODE IS ON. Do not run this configuration anywhere real: docs routes are exposed%s.",
                    " and no gateway key is required" if gateway_key is None else "")
    return AccessConfig(gateway_key, audit_key, dev)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8", "replace")).digest()


def key_matches(supplied: str | None, expected: str) -> bool:
    """Constant-time comparison. Both sides are hashed first so length does not leak."""
    return hmac.compare_digest(_digest(supplied or ""), _digest(expected)) and supplied is not None


def gateway_ok(cfg: AccessConfig, supplied: str | None) -> bool:
    return True if cfg.gateway_key is None else key_matches(supplied, cfg.gateway_key)


def audit_ok(cfg: AccessConfig, supplied: str | None) -> bool:
    """False when the audit view is off (no audit key configured) or the key is missing or wrong."""
    return cfg.audit_key is not None and key_matches(supplied, cfg.audit_key)


# ---- HIV scrubbing of worker responses (D82) ----
class _Counter:
    def __init__(self) -> None:
        self._n = 0
        self._lock = threading.Lock()

    def add(self, n: int) -> None:
        with self._lock:
            self._n += n

    @property
    def count(self) -> int:
        return self._n


SCRUB_EVENTS = _Counter()   # fields dropped by the fail-closed scan, since process start


def contains_hiv(text: str) -> bool:
    return "hiv" in text.lower()


def _scrub(obj, dropped: list[int]):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if contains_hiv(str(k)):
                dropped[0] += 1
                continue
            cleaned = _scrub(v, dropped)
            if cleaned is _DROP:
                dropped[0] += 1
                continue
            out[k] = cleaned
        return out
    if isinstance(obj, (list, tuple)):
        items = []
        for v in obj:
            cleaned = _scrub(v, dropped)
            if cleaned is _DROP:
                dropped[0] += 1
                continue
            items.append(cleaned)
        return items
    if isinstance(obj, str) and contains_hiv(obj):
        return _DROP
    return obj


_DROP = object()


def scrub_worker(view: dict) -> dict:
    """Return a copy of a worker response with every key or string value containing 'hiv' (any case) dropped.

    This is the last line of defence, not the design: the worker view is built without HIV content. If this
    ever drops something, a bug let it through, so the event is counted and logged (count only, never content).
    """
    dropped = [0]
    clean = _scrub(view, dropped)
    if dropped[0]:
        SCRUB_EVENTS.add(dropped[0])
        log.error("worker response: %d field(s) dropped by the HIV scan (this indicates a bug)", dropped[0])
    return clean
