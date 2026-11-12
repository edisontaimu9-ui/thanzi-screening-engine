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
    deep_recording_error: RecordingError | None = Field(
        default=None, description="Second advisory flag from a small neural network, beside recording_error. "
                                  "Present only when the deep models are loaded. Same meaning, same limits.")


class RiskDriver(BaseModel):
    feature: str
    text: str = Field(description="Plain-language statement of the finding that raised the estimate.")
    direction: str = Field(description="Always raises: only findings that raise the estimate are shown.")


class RiskOut(BaseModel):
    """Advisory clinical risk estimate. It can only add a concern: it never changes the classification, tier or referral,
    and the absence of a concern (`elevated` false, no message) must never be shown to a worker as reassurance."""
    available: bool
    scored: bool = Field(description="false when the child could not be scored: see not_scored_reason.")
    not_scored_reason: str | None = Field(description="age_outside_model_range, muac_missing, measurement_not_assessable, "
                                                      "possible_recording_error, data_quality_check_unavailable, invalid_input or model_error.")
    not_scored_message: str | None
    elevated: bool | None = Field(description="true: the model sees a higher than usual chance. false: no extra concern (not reassurance). null: not scored.")
    message: str | None = Field(description="Present only when elevated.")
    drivers: list[RiskDriver] = Field(description="Up to 3 findings that raised the estimate. Only when elevated.")
    target: str
    horizon_weeks: int
    model_version: str
    non_clinical: bool = Field(description="true for a model trained on simulated outcomes. Never use such a result for care.")
    advisory: str
    probability: float | None = Field(default=None, description="Calibrated probability. Audit view only.")
    raw_probability: float | None = Field(default=None, description="Before calibration. Audit view only.")
    threshold: float | None = Field(default=None, description="Audit view only.")
    model_kind: str | None = Field(default=None, description="logistic, gbm_logit or rf_prob. Audit view only.")
    provenance: str | None = Field(default=None, description="simulated or real. Audit view only.")
    explanation: dict[str, Any] | None = Field(default=None, description="Exact per-feature contributions. Audit view only.")


class IndicatorTrendOut(BaseModel):
    indicator: str = Field(description="weight_for_age, length_height_for_age or head_circumference_for_age.")
    assessed: bool
    reason: str | None = Field(description="Why it was not assessed: interval_too_short, implausible_measurement, "
                                           "outside_reference_ages, oedema_weight_unreliable. null when assessed.")
    z_previous: float | None
    z_current: float | None
    z_change: float | None
    direction: str | None = Field(description="fell, rose or steady. Weight and length are flagged only for a fall; head size for either.")
    lines_crossed: list[int] = Field(description="Whole z-score lines (-3 to +3) between the two values.")
    status_change: str | None = Field(description="below_minus2 or below_minus3 when newly below that line (weight and length only).")
    flagged: bool
    messages: list[str]
    reference: str
    guide: str


class GrowthTrendsOut(BaseModel):
    weight_for_age: IndicatorTrendOut | None = None
    length_height_for_age: IndicatorTrendOut | None = Field(
        default=None, description="Present only when both visits gave a length or height with its position.")
    head_circumference_for_age: IndicatorTrendOut | None = Field(
        default=None, description="Present only when both visits gave a head circumference.")


class GrowthMonitoring(BaseModel):
    assessed: bool
    reason: str | None = Field(description="Why it was not assessed: interval_too_short, implausible_weight, reference_unverified, "
                                           "outside_reference_ages. null when assessed.")
    status: str | None = Field(description="below_range, within_range or above_range. null when not assessed.")
    flagged: bool = Field(description="true only for below_range, including weight loss. Advisory.")
    weight_loss: bool
    interval_days: int
    weight_change_g: float | None
    rate_g_per_day: float | None
    reference_low: float | None = Field(description="g per day, averaged over the age bands the interval covers.")
    reference_high: float | None
    messages: list[str]
    reference: str
    advisory: str
    reference_derived: bool = Field(default=False, description="true when the weight-gain range used was derived, not published "
                                                               "(girls 3 to 6 months).")
    trends: GrowthTrendsOut = Field(default_factory=GrowthTrendsOut, description="z-score trends across the two visits.")
    review_suggested: bool = Field(default=False, description="true when the weight-gain result or any trend is flagged. "
                                                              "Advisory: a clinician should review the child's growth.")
    review_note: str | None = None


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
    route: str | None = Field(default=None, description="Only when birth context was given: under5 or under5_corrected_age.")
    birth_context: "BirthContext | None" = None
    growth_monitoring: GrowthMonitoring | None = Field(
        default=None, description="Only when previous_measurement was given and the baby is screened on the under-5 route. "
                                  "Advisory: never changes the classification.")
    ml_risk: RiskOut | None = Field(
        default=None, description="Only when the risk model is switched on (THANZI_RISK_ENABLED=1) and the baby is screened on the plain "
                                  "under-5 route. Advisory, escalate only: never changes the classification.")
    clinical_assessment: "ClinicalAssessment | None" = Field(
        default=None, description="Only when a baby under 2500 g has no gestational age: flagged for clinical assessment.")


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
    deep_model_version: str | None = Field(default=None, description="null when the deep models are not loaded.")
    risk_model_version: str | None = Field(default=None, description="null when the risk model is off or not loaded.")
    status: str
    disclaimer: str


class LatencyStats(BaseModel):
    calls_measured: int = Field(description="How many recent /v1/screen calls the figures cover (at most `window`).")
    window: int
    p50_ms: float | None = Field(description="null until a screening call has been made.")
    p95_ms: float | None
    max_ms: float | None
    mean_ms: float | None


class MetricsResponse(BaseModel):
    """Counts and durations only. Never a body, a value, an address or anything about a child (D176)."""
    since: float = Field(description="When this process started, Unix seconds.")
    uptime_seconds: float
    requests_total: int
    server_errors: int = Field(description="Responses with a 5xx status.")
    by_route: dict[str, int] = Field(description="Requests per known route. Anything else is counted under `other`.")
    by_status: dict[str, int] = Field(description="Responses per HTTP status code.")
    screen_latency: LatencyStats
    scope: str = Field(description="process: held in memory, reset on restart, one count per worker process.")


class ComponentInfo(BaseModel):
    name: str
    state: str = Field(description="ok, degraded, off or not_run. For the LLM service see its own /v1/llm/health.")
    version: str | None = None
    detail: str


class AboutResponse(BaseModel):
    """What this service is and what is running inside it. Read-only, no child data."""
    service: str
    api_version: str
    engine_version: str
    rule_set_version: str
    status: str
    disclaimer: str
    health: str = Field(description="ok, or degraded when the ML models are missing or mismatched. Same as /health.")
    uptime_seconds: float
    components: list[ComponentInfo] = Field(
        description="screening_engine, ml_logistic, ml_deep, ml_risk, growth_monitoring and llm_service, in that order.")
    routes: list[str]


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
    corrected_age_end_provisional: bool = Field(default=False, description="True while the corrected-age end point in use is provisional (GA 32 to under 37 weeks).")


class ClinicalAssessment(BaseModel):
    needed: bool
    reasons: list[CodeMessage]


class PretermResponse(BaseModel):
    """Preterm route (born under 37 weeks or under 2500 g, under 50 weeks post-menstrual age). No HIV content."""
    view: str = "worker"
    route: str = "preterm"
    worker_summary: list[str]
    tier: str | None = Field(description="The under-5 tier this preterm level maps to (docs/modules/preterm.md). Null for follow_up: it has no under-5 tier, use preterm_level.")
    tier_note: str | None = None
    preterm_level: str = Field(description="routine, follow_up, refer or urgent_refer.")
    reasons: list[str]
    actions: list[str]
    birth_context: BirthContext
    pma_weeks: float
    birth_classification: dict[str, str]
    measurements: dict[str, Any] = Field(description="Fenton 2025 Preterm Growth Chart z-score and percentile per measure, or 'outside_fenton_range'.")
    growth: dict[str, Any] | None = Field(description="Change in z-score from birth. Never a diagnosis from one percentile.")
    feeding: dict[str, Any]
    kmc: str
    supplements: list[str]
    handover: str | None = None
    note: str
    warnings: list[str]
    rule_set_version: str
    model_version: str
    data_attribution: str = Field(description="Fenton 2025 Preterm Growth Chart data, CC BY-NC-ND 4.0, attribution required, non-commercial.")
    status: str
    disclaimer: str


class PretermAuditResponse(PretermResponse):
    view: str = "audit"
    engine_output: dict[str, Any] = Field(description="The preterm engine's own output, before the oedema rule.")
    ml_features: dict[str, float | None] = Field(description="features() row. Context only. rule_level is never a label.")


for _m in (WorkerResponse, AuditResponse):
    _m.model_rebuild()


class HotspotArea(BaseModel):
    district: str
    status: str = Field(description="hotspot, watch, not_flagged, insufficient_data or no_data.")
    screened: int | None
    sam: int | None = Field(description="null when counts_suppressed.")
    mam: int | None = Field(description="null when counts_suppressed.")
    gam_cases: int | None = Field(description="SAM plus MAM. null when counts_suppressed.")
    prevalence: float | None
    ci_low: float | None = Field(description="Lower bound of the Wilson 95% interval.")
    ci_high: float | None
    reference_rate: float | None
    reference_kind: str | None = Field(description="supplied or batch_leave_one_out.")
    trend: str = Field(description="rising, falling, steady or not_assessed, against the previous month in the batch.")
    previous_prevalence: float | None
    data_quality_review: bool = Field(description="true when many screened children were UNABLE_TO_CLASSIFY.")
    counts_suppressed: bool
    reasons: list[str]


class HotspotResponse(BaseModel):
    period: str
    config_version: str
    areas: list[HotspotArea]
    summary: dict[str, int]
    min_screened: int
    advisory: str
