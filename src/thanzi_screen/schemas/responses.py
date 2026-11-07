"""Response models. Documentation of the contract only: responses are built and scrubbed as plain dicts."""
from typing import Any

from pydantic import BaseModel, Field


class CodeMessage(BaseModel):
    code: str
    message: str


class RecordingError(BaseModel):
    flagged: bool
    suggested_field: str | None
    messages: list[str]
    probability: float | None = Field(default=None, description="Audit view only.")


class Review(BaseModel):
    needed: bool
    reasons: list[CodeMessage]


class MlFlagsOut(BaseModel):
    available: bool = Field(description="false in degraded mode (models missing or mismatched).")
    recording_error: RecordingError | None
    review: Review
    advisory: str | None = None


class WorkerResponse(BaseModel):
    view: str = "worker"
    worker_summary: list[str] = Field(description="2-3 lines. Never contains HIV information.")
    classification: str
    tier: str
    programme: str | None = Field(description="null for every MAM child: the programme is shown in the audit view only.")
    rules_fired: list[str] = Field(description="Display codes. MAM.HIV_OTP and MAM.SFP both show as MAM.REFER.")
    reasons: list[CodeMessage]
    warnings: list[str]
    ml_flags: MlFlagsOut
    rule_set_version: str
    model_version: str
    status: str
    disclaimer: str


class AuditResponse(WorkerResponse):
    view: str = "audit"
    programme: str | None
    rules_fired: list[str] = Field(description="Real engine rule codes.")
    referral_text: str = Field(description="Raw Phase 2 referral text. May contain HIV information.")
    explanation: dict[str, Any] = Field(description="Full Phase 5 Explanation: traces, contributions, margins, audit notes.")


class ErrorBody(BaseModel):
    code: str
    message: str
    fields: list[str] | None = None


class HealthResponse(BaseModel):
    status: str = Field(description="ok, or degraded when the ML models are missing or mismatched.")


class VersionResponse(BaseModel):
    api_version: str
    engine_version: str
    rule_set_version: str
    model_version: str
    status: str
    disclaimer: str
