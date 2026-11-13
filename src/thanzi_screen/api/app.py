"""Thin FastAPI app (Phase 6). All logic lives in `service`; access control in `security`.

Run: `uvicorn --factory thanzi_screen.api.app:create_app_from_env`
Needs THANZI_GATEWAY_KEY (the service refuses to start without it). See docs/modules/api.md.
"""
import contextlib
import logging
import os
import time
from typing import Literal, Union

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from .. import __version__
from ..ml.dl import DeepModels, load_deep_models
from ..ml.flags import Models, load_models
from ..ml.risk import RiskModel, load_risk_model
from ..prediction import PredictionModel
from ..prediction.model import load_prediction_models
from ..schemas import (
    AboutResponse, AuditResponse, ErrorBody, HealthResponse, HotspotRequest, HotspotResponse, MetricsResponse, PretermAuditResponse, PretermResponse,
    ScreenRequest, VersionResponse, WorkerResponse,
)
from ..llm import LLMClient
from . import llm_routes, security, service
from .metrics import Metrics

log = logging.getLogger("thanzi.api")
MAX_BODY_BYTES = 16_384
HOTSPOT_PATH = "/v1/surveillance/hotspots"
MAX_HOTSPOT_BODY_BYTES = 262_144      # up to 1,000 grouped rows; still no child-level data
HEALTH_PATH = "/health"
_KNOWN_FIELDS = frozenset(service.ALLOWED) | {"view", "rows", "reference_rate", "district", "period", "screened", "sam", "mam",
                                              "unable"}


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


def _deep_enabled() -> bool:
    return os.environ.get("THANZI_DEEP_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _load_deep(deep: DeepModels | None, models_dir) -> DeepModels | None:
    """Second advisory flag (D153). Off with THANZI_DEEP_ENABLED=0. Missing or mismatched files: the flag is simply absent."""
    if deep is not None:
        return deep
    if not _deep_enabled():
        log.info("Deep flag switched off by THANZI_DEEP_ENABLED.")
        return None
    try:
        return load_deep_models(models_dir or os.environ.get("THANZI_MODELS_DIR") or None)
    except Exception as exc:
        log.warning("Deep models unavailable (%s). The deep flag is off.", type(exc).__name__)
        return None


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _load_risk(risk: RiskModel | None, models_dir) -> tuple[RiskModel | None, str]:
    """Advisory risk model. Off unless THANZI_RISK_ENABLED=1. A refused or missing model means no risk block, never a
    failed start: returns (model, state) with state ok, off or degraded. Simulated models need THANZI_RISK_ALLOW_SIMULATED=1."""
    if risk is not None:
        return risk, "ok"
    if not _flag("THANZI_RISK_ENABLED"):
        return None, "off"
    directory = os.environ.get("THANZI_RISK_MODEL_DIR") or (os.path.join(models_dir, "risk") if models_dir else None)
    try:
        return load_risk_model(directory, allow_simulated=_flag("THANZI_RISK_ALLOW_SIMULATED")), "ok"
    except Exception as exc:        # type only: never the message
        log.warning("Risk model unavailable (%s). The risk block is off.", type(exc).__name__)
        return None, "degraded"


def _load_prediction(model) -> tuple[tuple | None, str]:
    """Advisory prediction models, one per target and pathway. Off unless THANZI_PREDICTION_ENABLED=1; THANZI_PREDICTION_MODEL is one
    exported file, a folder of them, or a comma-separated list. A refused file is skipped; none usable means no block, never a failed
    start. Simulated files need THANZI_PREDICTION_ALLOW_SIMULATED=1. State: ok (all loaded), degraded (some or all refused), off."""
    if model is not None:
        return (tuple(model) if isinstance(model, (list, tuple)) else (model,)), "ok"
    if not _flag("THANZI_PREDICTION_ENABLED"):
        return None, "off"
    models, refused = load_prediction_models(os.environ.get("THANZI_PREDICTION_MODEL"), _flag("THANZI_PREDICTION_ALLOW_SIMULATED"))
    if not models:
        log.warning("No prediction model could be loaded. The prediction block is off.")
        return None, "degraded"
    return tuple(models), "degraded" if refused else "ok"


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    client = getattr(app.state, "llm", None)
    if client is not None:                       # optional local LLM client (D128): release its connections
        await client.aclose()


def create_app(models: Models | None = None, gateway_key: str | None = None, audit_key: str | None = None,
               dev_mode: bool = False, models_dir=None, llm: LLMClient | None = None,
               deep_models: DeepModels | None = None, risk_model: RiskModel | None = None, prediction_model: "PredictionModel | list | tuple | None" = None) -> FastAPI:
    """Build the app. Raises security.ConfigError if no gateway key is configured (unless dev mode).

    The local LLM routes exist only when `llm` is given or THANZI_LLM_ENABLED=1 (an invalid LLM configuration
    raises LLMConfigError). They are separate from screening: see api/llm_routes.py.
    """
    cfg = security.build_config(gateway_key, audit_key, dev_mode)
    loaded = _load_models(models, models_dir)
    loaded_deep = _load_deep(deep_models, models_dir)
    loaded_risk, risk_state = _load_risk(risk_model, models_dir)
    loaded_pred, pred_state = _load_prediction(prediction_model)
    llm_client = llm if llm is not None else llm_routes.client_from_env()
    docs = cfg.dev_mode
    app = FastAPI(
        title="Thanzi screening engine API", version=__version__,
        description="Decision support for under-five malnutrition screening (Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016). Not a diagnosis. "
                    "Babies born under 37 weeks or under 2500 g are routed to the preterm engine (Fenton 2025, CC BY-NC-ND 4.0) "
                    "until 50 weeks post-menstrual age, then screened on corrected age. "
                    "Demonstration only: synthetic data, not validated on real children. Stateless. "
                    "Sits behind the gateway: every route except /health needs X-Gateway-Key.",
        docs_url="/docs" if docs else None, redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None, lifespan=_lifespan)
    app.state.models, app.state.config, app.state.deep = loaded, cfg, loaded_deep
    app.state.risk, app.state.risk_state = loaded_risk, risk_state
    app.state.prediction, app.state.prediction_state = loaded_pred, pred_state
    app.state.metrics = metrics = Metrics()

    # ---- access control: before routing and before body validation, so nothing leaks to unauthenticated callers ----
    @app.middleware("http")
    async def gateway_guard(request: Request, call_next):
        if request.url.path != HEALTH_PATH:
            if not security.gateway_ok(cfg, request.headers.get(security.GATEWAY_HEADER)):
                return _error(401, "unauthorised", "Unauthorised.")
            length = request.headers.get("content-length")
            limit = MAX_HOTSPOT_BODY_BYTES if request.url.path == HOTSPOT_PATH else MAX_BODY_BYTES
            if length and length.isdigit() and int(length) > limit:
                return _error(413, "payload_too_large", "Request body is too large.")
        return await call_next(request)

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        """Outermost, so refused calls (401, 413) are counted too. Records the route label, status and duration only (D176)."""
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            metrics.record(request.url.path, status, time.perf_counter() - t0)

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
        return service.version_info(app.state.models, app.state.deep, app.state.risk, app.state.prediction)

    @app.get("/v1/about", response_model=AboutResponse, tags=["ops"])
    def about():
        """What is running: versions and state of the engine, the ML models, growth monitoring and the optional LLM service."""
        paths = sorted(p for p in app.openapi()["paths"] if p.startswith(("/v1/", "/health", "/version")))
        optional = [llm_routes.about_component(getattr(app.state, "llm", None))]
        return service.about_info(app.state.models, app.state.deep, optional, metrics.uptime_seconds(), paths,
                                  app.state.risk, app.state.risk_state, app.state.prediction, app.state.prediction_state)

    @app.get("/v1/metrics", response_model=MetricsResponse, tags=["ops"])
    def metrics_snapshot():
        """Request counts by route and status, and /v1/screen latency. Counts and durations only, in memory (D176)."""
        return {**metrics.snapshot(), "scope": "process"}

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
        return JSONResponse(service.screen(body.model_dump(), view, app.state.models, app.state.deep, app.state.risk, app.state.prediction))

    @app.post(HOTSPOT_PATH, response_model=HotspotResponse, tags=["surveillance"], responses={
        401: {"model": ErrorBody}, 413: {"model": ErrorBody}, 422: {"model": ErrorBody}})
    def hotspots(body: HotspotRequest):
        """Flag districts with higher SAM+MAM prevalence among screened children. Takes counts already grouped by the
        caller (no child records, no fine geography). Advisory only: never changes an individual classification."""
        return JSONResponse(service.hotspots(body.model_dump()))

    if llm_client is not None:
        llm_routes.install(app, llm_client)

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
