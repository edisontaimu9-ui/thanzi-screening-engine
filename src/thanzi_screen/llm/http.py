"""Small JSON-over-HTTP helper shared by the network providers. The only module that imports httpx, and only when
a network provider is built, so `import thanzi_screen.llm` works (and the mock provider runs) without it.

Hardening: no redirects are followed, proxy environment variables are ignored (a stray HTTPS_PROXY must not carry
private traffic out), replies are read in pieces and cut off at `max_response_bytes`, and no error text from the
server is ever copied into an exception.
"""
from __future__ import annotations

import json
from typing import Any

from .config import LLMConfig
from .errors import (LLMAuthError, LLMConfigError, LLMConnectionError, LLMModelNotFoundError, LLMRejectedError,
                     LLMResponseError, LLMServerError, LLMTimeoutError)

USER_AGENT = "thanzi-llm-client/1"


class JsonHttp:
    def __init__(self, config: LLMConfig, transport=None) -> None:
        try:
            import httpx
        except ImportError:
            raise LLMConfigError("The httpx package is needed for this provider. "
                                 "Install with: pip install -c constraints.txt \".[llm]\"") from None
        self._httpx = httpx
        self._cap = config.max_response_bytes
        self._request_timeout = config.request_timeout_s
        self._connect_timeout = config.connect_timeout_s
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if config.api_key:
            headers["Authorization"] = "Bearer " + config.api_key
        self._client = httpx.AsyncClient(
            base_url=config.endpoint + "/", headers=headers, follow_redirects=False, trust_env=False,
            transport=transport, timeout=self._timeout(self._request_timeout),
            limits=httpx.Limits(max_connections=config.max_concurrency + 2, max_keepalive_connections=1,
                                keepalive_expiry=30.0))

    def _timeout(self, read_s: float):
        return self._httpx.Timeout(connect=self._connect_timeout, read=read_s, write=self._connect_timeout,
                                   pool=self._connect_timeout)

    async def request_json(self, method: str, path: str, body: Any = None, timeout_s: float | None = None) -> Any:
        """Send, check the status, read at most `max_response_bytes` and return parsed JSON (object or list)."""
        httpx = self._httpx
        timeout = self._timeout(timeout_s if timeout_s is not None else self._request_timeout)
        try:
            async with self._client.stream(method, path.lstrip("/"), json=body, timeout=timeout) as response:
                status = response.status_code
                declared = response.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > self._cap:
                    raise LLMResponseError("The reply is larger than the configured limit.")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self._cap:
                        raise LLMResponseError("The reply is larger than the configured limit.")
                    chunks.append(chunk)
        except httpx.TimeoutException:
            raise LLMTimeoutError() from None
        except httpx.TransportError:
            raise LLMConnectionError() from None
        except httpx.HTTPError:
            raise LLMResponseError() from None
        self._raise_for_status(status)
        try:
            data = json.loads(b"".join(chunks))
        except (ValueError, UnicodeDecodeError):
            raise LLMResponseError("The reply was not valid JSON.") from None
        if not isinstance(data, (dict, list)):
            raise LLMResponseError("The reply was not a JSON object.")
        return data

    @staticmethod
    def _raise_for_status(status: int) -> None:
        if 200 <= status < 300:
            return
        if status in (401, 403):
            raise LLMAuthError()
        if status == 404:
            raise LLMModelNotFoundError()
        if status == 429 or status >= 500:
            raise LLMServerError(status)
        if 400 <= status < 500:
            raise LLMRejectedError(status)
        raise LLMResponseError("The server answered with an unexpected status.")     # 1xx and 3xx (no redirects)

    async def aclose(self) -> None:
        await self._client.aclose()
