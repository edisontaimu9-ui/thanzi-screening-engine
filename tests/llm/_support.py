"""Helpers for the LLM tests. All text sent to any model in these tests is synthetic."""
from __future__ import annotations

import asyncio
import importlib.util
import os

import pytest

# Obviously fake. Never put a real record, name or identifier in a test prompt.
SYNTHETIC_PROMPT = "Synthetic test note SYN-0001: child aged 14 months, caregiver reports a good appetite."
SYNTHETIC_MARKER = "SYN-0001"


def need_httpx() -> None:
    if importlib.util.find_spec("httpx") is None:
        if os.environ.get("THANZI_REQUIRE_API_TESTS") == "1":
            pytest.fail("LLM transport tests are required but httpx is not installed", pytrace=False)
        pytest.skip("httpx not installed", allow_module_level=True)


def run(coro):
    return asyncio.run(coro)
