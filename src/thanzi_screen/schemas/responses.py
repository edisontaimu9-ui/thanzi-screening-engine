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


class BirthContext(BaseModel):
    route: str = Field(description="under5, preterm or under5_corrected_age.")
    route_reason: str
    gestational_age_weeks: float | None
    birth_weight_g: float | None
    born_preterm: bool = Field(description="Gestational age under 37 weeks.")
    low_birth_weight: bool = Field(description="Birth weight under 2500 g.")
    age_days: int = Field(description="Chronological age.")
    pma_weeks: float | None = Field(description="Post-menstrual age: gestational age plus chronological age.")
    corrected_age_days: int | None
    corrected_age_until_chronological_months: int | None
    age_days_used: int = Field(description="The age the engine that ran was given.")
    birth_weight_class: str | None = Field(description="ELBW, VLBW, LBW or NORMAL.")


class PretermResponse(BaseModel):
    """Preterm route (born under 37 weeks or under 2500 g, under 50 weeks post-menstrual age). No HIV content."""
    view: str = "worker"
    route: str = "preterm"
    worker_summary: list[str]
    tier: str = Field(description="The under-5 tier this preterm level maps to (docs/modules/preterm.md).")
    preterm_level: str = Field(description="routine, follow_up, refer or urgent_refer.")
    reasons: list[str]
    actions: list[str]
    birth_context: BirthContext
    pma_weeks: float
    birth_classification: dict[str, str]
    measurements: dict[str, Any] = Field(description="Fenton 2025 z-score and percentile per measure, or 'outside_fenton_range'.")
    growth: dict[str, Any] | None = Field(description="Change in z-score from birth. Never a diagnosis from one percentile.")
    feeding: dict[str, Any]
    kmc: str
    supplements: list[str]
    handover: str | None = None
    note: str
    warnings: list[str]
    rule_set_version: str
    model_version: str
    data_attribution: str = Field(description="Fenton 2025 data, CC BY-NC-ND 4.0, attribution required, non-commercial.")
    status: str
    disclaimer: str


class PretermAuditResponse(PretermResponse):
    view: str = "audit"
    engine_output: dict[str, Any] = Field(description="The preterm engine's own output, before the oedema rule.")
    ml_features: dict[str, float | None] = Field(description="features() row. Context only. rule_level is never a label.")
