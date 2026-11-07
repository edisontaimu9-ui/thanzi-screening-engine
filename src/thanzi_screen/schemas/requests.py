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


class ScreenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    sex: Literal["male", "female"]
    age_days: int = Field(description="Age in whole days. No date of birth is accepted.")
    weight_kg: Number
    length_height_cm: Number
    measure_position: Literal["length", "height"]
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
