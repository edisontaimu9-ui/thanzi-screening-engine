"""Request contract. Strict types, unknown fields rejected (a name or child_id is a 422).

`null` or an omitted field means not assessed; an empty list means assessed, none present (D25).
Ranges and plausibility are the engine's (InputError), so there is one source of truth.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[float, Field(allow_inf_nan=False)]
DangerSignName = Literal["anorexia", "intractable_vomiting", "convulsions", "lethargy_not_alert", "unconsciousness",
                         "unable_to_drink_or_breastfeed", "high_fever"]
ComplicationName = Literal["hypoglycaemia", "hypothermia", "infections", "severe_dehydration", "shock",
                           "very_severe_anaemia", "cardiac_failure", "severe_dermatosis",
                           "vitamin_a_deficiency_signs", "diarrhoea", "malaria"]
NeonatalSignName = Literal["bilious_vomiting", "apnoea", "cyanosis", "abdominal_distension", "blood_in_stool",
                           "feed_intolerance"]


class PreviousMeasurement(BaseModel):
    """An earlier visit of the same child, for growth monitoring. The engine stores nothing, so the caller supplies it."""
    model_config = ConfigDict(extra="forbid", strict=True)

    age_days: int = Field(description="Age in whole days at that earlier visit. Must be before this visit.")
    weight_kg: Number = Field(description="Weight in kilograms at that earlier visit.")
    length_height_cm: Number | None = Field(
        default=None, description="Optional. Length or height at that visit, cm. With measure_position, adds the length/height-for-age trend.")
    measure_position: Literal["length", "height"] | None = Field(
        default=None, description="Required when length_height_cm is given: how that earlier visit was measured.")
    hc_cm: Number | None = Field(
        default=None, description="Optional. Head circumference at that visit, cm. With hc_cm on this visit, adds the head-circumference trend.")


class ScreenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sex: Literal["male", "female"]
    age_days: int = Field(description="Age in whole days. No date of birth is accepted.")
    weight_kg: Number
    length_height_cm: Number | None = Field(
        default=None, description="Required for the under-5 flow. Optional only when the baby is screened by the preterm "
        "engine (born under 37 weeks or under 2500 g, under 50 weeks post-menstrual age); the length z-score is skipped without it.")
    measure_position: Literal["length", "height"] | None = Field(
        default=None, description="Required whenever length_height_cm is given. Must be length on the preterm route.")
    oedema: Literal["none", "+", "++", "+++"] = Field(description="Required: it is never assumed to be absent.")
    muac_cm: Number | None = Field(default=None, description="6-59 months only. null: not measured.")
    appetite: Literal["passed", "failed", "not_done"] = "not_done"
    danger_signs: list[DangerSignName] | None = Field(default=None, max_length=30,
                                                      description="null: not assessed. []: assessed, none present.")
    complications: list[ComplicationName] | None = Field(default=None, max_length=30,
                                                         description="null: not assessed. []: assessed, none present.")
    clinically_well_and_alert: bool | None = None
    hiv_positive: bool | None = Field(default=None, description="Optional and sensitive. Never echoed in worker responses.")
    visible_severe_wasting: bool | None = None
    too_weak_to_suckle: bool | None = None
    failure_to_gain_weight: bool | None = None
    previous_measurement: PreviousMeasurement | None = Field(
        default=None, description="Optional earlier visit (age_days, weight_kg). With it the response adds growth_monitoring: "
        "weight gain per day compared with the reference range in the ASPEN Paediatric and Neonatal Nutrition Support Handbook, Third Edition, 2024, and z-score trends for weight, length or height, and head "
        "circumference (WHO Child Growth Standards, 2006). Advisory only. Under-5 route only.")

    # ---- Birth context and preterm fields (all optional). Without gestational_age_weeks and birth_weight_g the
    # request is screened exactly as before. See docs/modules/preterm.md for the routing rules. ----
    gestational_age_weeks: Number | None = Field(
        default=None, description="Gestational age at birth, decimal weeks (22 to 44). With birth_weight_g it decides "
        "routing: born under 37 weeks or under 2500 g goes to the preterm engine until 50 weeks post-menstrual age, "
        "then to the under-5 engine on corrected age.")
    birth_weight_g: Number | None = Field(default=None, description="Birth weight in GRAMS (weight_kg is kilograms).")
    hc_cm: Number | None = Field(default=None, description="Head circumference, cm. Preterm route. On the under-5 route it is used only for the head-circumference trend, when previous_measurement.hc_cm is also given.")
    birth_length_cm: Number | None = Field(default=None, description="Length at birth, cm. Preterm route only; needed for the length trend.")
    birth_hc_cm: Number | None = Field(default=None, description="Head circumference at birth, cm. Preterm route only; needed for the head-growth trend.")
    sick: bool | None = Field(default=None, description="Preterm route: clinician judges the baby sick (hospitalise).")
    apnoea_last_7_days: bool | None = Field(default=None, description="Preterm route: apnoea in the last 7 days.")
    temperature_unstable: bool | None = Field(default=None, description="Preterm route: unstable temperature.")
    consecutive_days_gaining_weight: int | None = Field(default=None, description="Preterm route: consecutive days of weight gain. If null and failure_to_gain_weight is true, 0 is used.")
    gastric_aspirate_pct: Number | None = Field(default=None, description="Preterm route: gastric aspirate as % of the last tube feed (0 to 100).")
    neonatal_danger_signs: list[NeonatalSignName] | None = Field(
        default=None, max_length=30, description="Preterm route: signs the danger-sign list of the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 does not have. "
        "null: not assessed. []: assessed, none present. Convulsions, lethargy, hypoglycaemia, severe dehydration and "
        "unable to feed are read from danger_signs, complications and too_weak_to_suckle, not asked twice.")
    hypoglycaemia_not_correcting: bool | None = Field(
        default=None, description="Preterm route: hypoglycaemia is not correcting with treatment (the urgent trigger). "
        "The complications value hypoglycaemia is itself an urgent trigger on the preterm route (Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, Table 5: inpatient).")


class HotspotRow(BaseModel):
    """Counts for one district in one month, already grouped by the caller. No child-level data."""
    model_config = ConfigDict(extra="forbid", strict=True)

    district: str = Field(description="District name only. No facility, community, village or coordinates.")
    period: str = Field(description="Month, YYYY-MM.")
    screened: int = Field(ge=0, description="Children under five screened in that month.")
    sam: int = Field(ge=0, description="Of those, classified SAM (SAM_OTP, SAM_INPATIENT or SAM_ASSESS).")
    mam: int = Field(ge=0, description="Of those, classified MAM.")
    unable: int = Field(default=0, ge=0, description="Of those, UNABLE_TO_CLASSIFY. Used for a data-quality flag.")


class HotspotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    rows: list[HotspotRow] = Field(min_length=1, max_length=1000,
                                   description="One row per district and month. The latest month is assessed; earlier months give the trend.")
    reference_rate: Number | None = Field(
        default=None, description="Optional fixed reference rate of SAM+MAM (0 to 1), for example a national survey figure. "
                                  "Default: the rate of all the other districts in the same batch.")


class OrgUnitIn(BaseModel):
    """One org unit of the reporting hierarchy: the national unit, a district or a facility. Names are place names only."""
    model_config = ConfigDict(extra="forbid", strict=True)

    code: str = Field(description="Org unit code, for example the DHIS2 code. Letters, digits, dot, dash and underscore, up to 50.")
    name: str = Field(description="Place name of the district or facility. Never a person.")
    level: Literal["national", "district", "facility"]
    parent: str | None = Field(default=None, description="Code of the parent: the national unit for a district, a district for a facility. "
                                                         "None for the national unit.")


class FacilityRowIn(BaseModel):
    """Counts for one facility in one month, already grouped by the caller. No child-level data."""
    model_config = ConfigDict(extra="forbid", strict=True)

    org_unit: str = Field(description="Code of a facility in org_units.")
    period: str = Field(description="Month, YYYY-MM.")
    screened: int = Field(ge=0, description="Children under five screened in that month.")
    sam: int = Field(ge=0, description="Of those, classified SAM (SAM_OTP, SAM_INPATIENT or SAM_ASSESS).")
    mam: int = Field(ge=0, description="Of those, classified MAM.")
    unable: int = Field(default=0, ge=0, description="Of those, UNABLE_TO_CLASSIFY.")


class SurveillanceReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    org_units: list[OrgUnitIn] = Field(min_length=1, max_length=3000, description="The whole hierarchy, so facilities that did not report are shown as not reported.")
    rows: list[FacilityRowIn] = Field(min_length=1, max_length=3000, description="One row per reporting facility and month. Earlier months give the district trend.")
    period: str | None = Field(default=None, description="Month to report, YYYY-MM. Default: the latest month in rows.")
    reference_rate: Number | None = Field(default=None, description="Optional fixed reference rate of SAM+MAM (0 to 1) for district hotspot status. "
                                                                    "Default: the other districts in the same batch.")


class Dhis2MappingIn(BaseModel):
    """Which DHIS2 data element and org unit each count goes to. Supplied by the DHIS2 administrators, never guessed."""
    model_config = ConfigDict(extra="forbid", strict=True)

    elements: dict[str, str] = Field(description="Data element id for each count: screened, sam and mam are required, unable is optional.")
    data_set: str | None = Field(default=None, description="Optional data set id, in the data element id scheme.")
    data_element_id_scheme: Literal["CODE", "UID"] = "CODE"
    org_unit_id_scheme: Literal["CODE", "UID"] = "CODE"
    org_units: dict[str, str] = Field(default_factory=dict, description="Engine org unit code to DHIS2 org unit id. Needed for every facility with the UID scheme. "
                                                                         "With the CODE scheme it overrides the engine code.")


class Dhis2ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    org_units: list[OrgUnitIn] = Field(min_length=1, max_length=3000)
    rows: list[FacilityRowIn] = Field(min_length=1, max_length=3000)
    mapping: Dhis2MappingIn
    period: str | None = Field(default=None, description="Month to export, YYYY-MM. Default: the latest month in rows.")
