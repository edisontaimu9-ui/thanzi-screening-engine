"""Optional HTTP routes for the local LLM client (D128-D133). Off unless THANZI_LLM_ENABLED=1.

Independence: these routes call `thanzi_screen.llm` only. `service.screen` and every clinical module know nothing
about the model, and `/health` (the container health check) ignores it. A dead model server never changes a
screening result or the screening health status.

Both routes sit behind the gateway key like every route except /health. Nothing here logs a prompt or a reply.
"""
from __future__ import annotations

import os
from typing import Mapping

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..llm import (LLMAuthError, LLMBadRequestError, LLMBusyError, LLMClient, LLMConnectionError, LLMError,
                   LLMModelNotFoundError, LLMResponseError, LLMServerError, LLMTimeoutError, build_client,
                   enabled_from_env)

NOTICE = ("Generated text is not a screening result. It must not be used to classify, refer or diagnose, "
          "and it is never an input to the screening rules.")

# error class -> HTTP status. Anything not listed is a 502.
_STATUS = {LLMBadRequestError: 422, LLMBusyError: 503, LLMConnectionError: 503, LLMModelNotFoundError: 503,
           LLMAuthError: 503, LLMServerError: 503, LLMTimeoutError: 504, LLMResponseError: 502}


class GenerateRequest(BaseModel):
    """Free text only. Synthetic or non-identifying text: this endpoint is not for patient records."""
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=4000)
    system: str | None = Field(default=None, min_length=1, max_length=2000)
    max_tokens: int | None = Field(default=None, ge=1, le=1024)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class GenerateResponse(BaseModel):
    text: str
    model: str
    provider: str
    finish_reason: str
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    notice: str = NOTICE


class LLMHealthResponse(BaseModel):
    state: str
    provider: str
    model: str
    detail: str
    model_available: bool | None = None
    latency_ms: float | None = None


class LLMErrorBody(BaseModel):
    code: str
    message: str


def client_from_env(env: Mapping[str, str] | None = None) -> LLMClient | None:
    """None unless THANZI_LLM_ENABLED=1. An enabled but invalid configuration raises LLMConfigError: fail closed."""
    env = os.environ if env is None else env
    return build_client(env=env) if enabled_from_env(env) else None


def _error(exc: LLMError) -> JSONResponse:
    status = next((s for cls, s in _STATUS.items() if isinstance(exc, cls)), 502)
    headers = {"Retry-After": "5"} if isinstance(exc, LLMBusyError) else None
    return JSONResponse(status_code=status, content={"code": exc.code, "message": str(exc)}, headers=headers)


def install(app: FastAPI, client: LLMClient) -> None:
    """Add the routes and keep the client on `app.state.llm` (closed on shutdown by the app's lifespan)."""
    app.state.llm = client
    router = APIRouter(prefix="/v1/llm", tags=["llm"])
    errors = {s: {"model": LLMErrorBody} for s in (422, 502, 503, 504)}

    @router.get("/health", response_model=LLMHealthResponse, responses={503: {"model": LLMHealthResponse}})
    async def llm_health():
        """200 when the model server is usable (ok or degraded), 503 when it is not. Never touches screening."""
        status = await client.health()
        return JSONResponse(status_code=503 if status.state == "unavailable" else 200, content=status.as_dict())

    @router.post("/generate", response_model=GenerateResponse, responses=errors)
    async def llm_generate(body: GenerateRequest):
        """Advisory text from the local model. Not part of screening."""
        try:
            params = client.config.params.with_overrides(max_tokens=body.max_tokens, temperature=body.temperature)
            result = await client.generate(body.prompt, system=body.system, params=params)
        except LLMError as exc:
            return _error(exc)
        usage = result.usage
        return GenerateResponse(
            text=result.text, model=result.model, provider=result.provider, finish_reason=result.finish_reason,
            latency_ms=round(result.latency_ms, 1), prompt_tokens=None if usage is None else usage.prompt_tokens,
            completion_tokens=None if usage is None else usage.completion_tokens)

    app.include_router(router)
