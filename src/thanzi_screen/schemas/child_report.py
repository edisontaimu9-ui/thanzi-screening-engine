"""Response model for the individual child report (Phase 9). Documentation of the contract only: the report is built as a plain dict."""
from typing import Any

from pydantic import BaseModel, Field


class ReportWording(BaseModel):
    version: str
    status: str = Field(description="draft_pending_clinical_review until the wording is signed off.")
    notice: str


class ReportAttention(BaseModel):
    level: str = Field(description="routine, raised, recheck or urgent. Set by the screening tier. A growth or prediction finding can lift "
                                   "routine to raised. Nothing lowers a level.")
    label: str
    raised_by_findings: bool = Field(description="true when a growth or prediction finding lifted the level above the one the screening tier sets.")
    changes_classification: bool = Field(description="Always false.")


class ReportResult(BaseModel):
    """The screening result, copied from the worker view. Never recomputed."""
    route: str
    classification: str | None = Field(description="Null on the preterm route.")
    tier: str | None
    programme: str | None = Field(description="Null for every moderate case, as in the worker view.")
    rules_fired: list[str]
    preterm_level: str | None = Field(description="Preterm route only.")
    birth_classification: dict[str, str] | None = Field(description="Preterm route only.")
    summary: list[str]
    reasons: list[str]
    rule_set_version: str | None


class ReportAction(BaseModel):
    statement: str
    steps: list[str] = Field(description="Preterm route: the actions of the preterm engine, as in the worker view.")
    note: str | None = None


class ReportCheckItem(BaseModel):
    source: str = Field(description="recording_error, review, clinical_assessment or warning.")
    text: str
    field: str | None = None


class ReportCheck(BaseModel):
    lead: str
    items: list[ReportCheckItem]


class ReportGrowth(BaseModel):
    assessed: bool
    review_suggested: bool
    lead: str
    messages: list[str]
    review_note: str | None = None


class ReportConcern(BaseModel):
    plain: str | None = None
    stratum: str | None = None


class ReportNotScored(BaseModel):
    target: str | None = None
    reason: str | None = None
    message: str | None = None


class ReportPrediction(BaseModel):
    """Only the status of the advisory estimate. No concern is NOT reassurance, and a target that was not scored has no estimate."""
    status: str = Field(description="concern, no_concern, not_scored or not_run.")
    elevated: bool
    statement: str
    message: str | None = Field(description="The consolidated prediction sentence, copied. Present only for a concern.")
    concerns: list[ReportConcern]
    drivers: list[str]
    not_scored: list[ReportNotScored]


class ChildReportResponse(BaseModel):
    """Individual child screening report, built from the worker view only. Screening is not diagnosis. Wording is draft."""
    report_version: str
    wording: ReportWording
    not_a_diagnosis: str
    attention: ReportAttention
    result: ReportResult
    action: ReportAction
    check_before_acting: ReportCheck | None = Field(description="Null when there is nothing to check.")
    growth: ReportGrowth | None = Field(description="Only when previous_measurement was given on the under-5 route.")
    prediction: ReportPrediction
    limits: list[str]
    sources: list[str]
