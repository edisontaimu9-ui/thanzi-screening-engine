"""Thin FastAPI app (Phase 6). All logic lives in `service`; access control in `security`.

Run: `uvicorn --factory thanzi_screen.api.app:create_app_from_env`
Needs THANZI_GATEWAY_KEY (the service refuses to start without it). See docs/modules/api.md.
"""
import logging
import os
from typing import Literal, Union

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from .. import __version__
from ..ml.flags import Models, load_models
from ..schemas import (
    AuditResponse, ErrorBody, HealthResponse, PretermAuditResponse, PretermResponse, ScreenRequest, VersionResponse,
    WorkerResponse,
)
from . import security, service

log = logging.getLogger("thanzi.api")
MAX_BODY_BYTES = 16_384
HEALTH_PATH = "/health"
_KNOWN_FIELDS = frozenset(service.ALLOWED) | {"view"}


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "message": message, **extra})


def _load_models(models: Models | None, models_dir) -> Models | None:
    if models is not None:
        return models
    try:
        return load_models(models_dir or os.environ.get("THANZI_MODELS_DIR") or None)
    except Exception as exc:        # missing, unreadable or mismatched: start degraded, say why by type only
        log.warning("ML models unavailable (%s). Starting in degraded mode.", type(exc).__name__)
        return None


def create_app(models: Models | None = None, gateway_key: str | None = None, audit_key: str | None = None,
               dev_mode: bool = False, models_dir=None) -> FastAPI:
    """Build the app. Raises security.ConfigError if no gateway key is configured (unless dev mode)."""
    cfg = security.build_config(gateway_key, audit_key, dev_mode)
    loaded = _load_models(models, models_dir)
    docs = cfg.dev_mode
    app = FastAPI(
        title="Thanzi screening engine API", version=__version__,
        description="Decision support for under-five malnutrition screening (CMAM 2016). Not a diagnosis. "
                    "Babies born under 37 weeks or under 2500 g are routed to the preterm engine (Fenton 2025, CC BY-NC-ND 4.0) "
                    "until 50 weeks post-menstrual age, then screened on corrected age. "
                    "Demonstration only: synthetic data, not validated on real children. Stateless. "
                    "Sits behind the gateway: every route except /health needs X-Gateway-Key.",
        docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None)
    app.state.models, app.state.config = loaded, cfg

    # ---- access control: before routing and before body validation, so nothing leaks to unauthenticated callers ----
    @app.middleware("http")
    async def gateway_guard(request: Request, call_next):
        if request.url.path != HEALTH_PATH:
            if not security.gateway_ok(cfg, request.headers.get(security.GATEWAY_HEADER)):
                return _error(401, "unauthorised", "Unauthorised.")
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
                return _error(413, "payload_too_large", "Request body is too large.")
        return await call_next(request)

    # ---- errors: stable codes, never the submitted values ----
    @app.exception_handler(service.ApiError)
    async def api_error(_: Request, exc: service.ApiError):
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError):
        unknown, fields, bad_json = False, [], False
        for e in exc.errors():
            loc = [str(p) for p in e.get("loc", ())]
            name = loc[-1] if loc and loc[-1] in _KNOWN_FIELDS else None
            if e.get("type") == "extra_forbidden":
                unknown = True
            elif e.get("type") == "json_invalid":
                bad_json = True
            elif name and name not in fields:
                fields.append(name)
        if bad_json:
            return _error(422, "invalid_json", "The request body is not valid JSON.")
        if unknown:
            return _error(422, "unknown_field", "The request contains a field that is not accepted. "
                          "Names, identifiers and dates of birth are never accepted.", fields=fields or None)
        return _error(422, "invalid_request", "The request is missing a field or has a field with the wrong type or value.",
                      fields=fields or None)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.error("unhandled error: %s", type(exc).__name__)      # type only: never the message or the input
        return _error(500, "internal_error", "Internal error.")

    # ---- routes ----
    @app.get(HEALTH_PATH, response_model=HealthResponse, tags=["ops"])
    def health():
        """No credential needed and nothing else returned, so a container health check works."""
        return {"status": "ok" if app.state.models is not None else "degraded"}

    @app.get("/version", response_model=VersionResponse, tags=["ops"])
    def version():
        return service.version_info(app.state.models)

    @app.post("/v1/screen", tags=["screen"], responses={
        200: {"model": Union[WorkerResponse, AuditResponse, PretermResponse, PretermAuditResponse],
              "description": "Worker view by default. view=audit returns the audit view. A baby routed to the preterm "
                             "engine gets the preterm response (route=preterm)."},
        401: {"model": ErrorBody}, 403: {"model": ErrorBody}, 413: {"model": ErrorBody}, 422: {"model": ErrorBody}})
    def screen(body: ScreenRequest, view: Literal["worker", "audit"] = "worker",
               x_audit_key: str | None = Header(default=None, alias=security.AUDIT_HEADER)):
        """Screen one child. Worker view never contains HIV information. Audit view needs X-Audit-Key."""
        if view == "audit" and not security.audit_ok(cfg, x_audit_key):
            return _error(403, "audit_forbidden", "The audit view is not available.")
        return JSONResponse(service.screen(body.model_dump(), view, app.state.models))

    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
            schema.setdefault("components", {}).setdefault("securitySchemes", {})["GatewayKey"] = {
                "type": "apiKey", "in": "header", "name": security.GATEWAY_HEADER}
            for path, ops in schema["paths"].items():
                if path != HEALTH_PATH:
                    for op in ops.values():
                        op["security"] = [{"GatewayKey": []}]
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    return app


def create_app_from_env() -> FastAPI:
    """Factory for uvicorn. Keys and the models directory come from the environment."""
    return create_app()
