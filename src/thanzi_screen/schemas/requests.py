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

    # ---- Birth context and preterm fields (all optional). Without gestational_age_weeks and birth_weight_g the
    # request is screened exactly as before. See docs/modules/preterm.md for the routing rules. ----
    gestational_age_weeks: Number | None = Field(
        default=None, description="Gestational age at birth, decimal weeks (22 to 44). With birth_weight_g it decides "
        "routing: born under 37 weeks or under 2500 g goes to the preterm engine until 50 weeks post-menstrual age, "
        "then to the under-5 engine on corrected age.")
    birth_weight_g: Number | None = Field(default=None, description="Birth weight in GRAMS (weight_kg is kilograms).")
    hc_cm: Number | None = Field(default=None, description="Head circumference, cm. Preterm route only.")
    birth_length_cm: Number | None = Field(default=None, description="Length at birth, cm. Preterm route only; needed for the length trend.")
    birth_hc_cm: Number | None = Field(default=None, description="Head circumference at birth, cm. Preterm route only; needed for the head-growth trend.")
    sick: bool | None = Field(default=None, description="Preterm route: clinician judges the baby sick (hospitalise).")
    apnoea_last_7_days: bool | None = Field(default=None, description="Preterm route: apnoea in the last 7 days.")
    temperature_unstable: bool | None = Field(default=None, description="Preterm route: unstable temperature.")
    consecutive_days_gaining_weight: int | None = Field(default=None, description="Preterm route: consecutive days of weight gain. If null and failure_to_gain_weight is true, 0 is used.")
    gastric_aspirate_pct: Number | None = Field(default=None, description="Preterm route: gastric aspirate as % of the last tube feed (0 to 100).")
    neonatal_danger_signs: list[NeonatalSignName] | None = Field(
        default=None, max_length=30, description="Preterm route: signs the CMAM danger-sign list does not have. "
        "null: not assessed. []: assessed, none present. Convulsions, lethargy, hypoglycaemia, severe dehydration and "
        "unable to feed are read from danger_signs, complications and too_weak_to_suckle, not asked twice.")
    hypoglycaemia_not_correcting: bool | None = Field(
        default=None, description="Preterm route: hypoglycaemia is not correcting with treatment (the urgent trigger). "
        "The complications value hypoglycaemia is itself an urgent trigger on the preterm route (CMAM 2016 Table 5: inpatient).")
