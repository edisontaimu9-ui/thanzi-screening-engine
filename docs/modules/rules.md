# Module: rules (Phase 2)

CMAM 2016 classification and referral. Rules only; no ML. Rule set `rules_v2016`.

## API
```python
from thanzi_screen.anthro import compute_anthropometry
from thanzi_screen.rules import classify, ClinicalInputs, Appetite, OedemaGrade

a = compute_anthropometry(sex="male", weight_kg=6.0, length_height_cm=68.0,
                          measure_position="length", age_days=300)
r = classify(a, ClinicalInputs(muac_cm=11.0, appetite=Appetite.PASSED,
             danger_signs=frozenset(), complications=frozenset(),
             clinically_well_and_alert=True))
r.classification, r.tier, r.programme, r.rules_fired, r.reasons, r.warnings, r.referral_text
```
`None` = not assessed. Empty frozenset = assessed, none present. Pass `oedema=True` to `compute_anthropometry` when oedema is present, and the grade in `ClinicalInputs`.

## Outputs
| Classification | Tier | Programme |
|---|---|---|
| LOW_RISK | low_risk | none |
| MAM | mam | SFP (OTP for HIV-positive meeting conditions) |
| SAM_OTP | urgent | OTP |
| SAM_INPATIENT | urgent | NRU |
| SAM_ASSESS | urgent | clinician decides OTP vs NRU |
| UNABLE_TO_CLASSIFY | recheck | none |

Every result carries `rules_fired` (IDs resolve in `RULES` with source, page, tag), `rule_set_version`, and the "decision support, not diagnosis" statement. Referral text is placeholder until official wording is extracted (D22, I10).

## Logic (child, >=6 months)
SAM if MUAC <11.5, WFL/H z <-3, or any bilateral pitting oedema. MAM if MUAC 11.5 to <12.5 or z -3 to <-2. Inpatient for oedema +++, oedema with severe wasting, or SAM with any danger sign, complication, or failed appetite test. OTP only when appetite passed, no danger signs or complications, and clinically well and alert; any missing item gives SAM_ASSESS. Low risk only when no criterion is met and a valid wasting measurement exists.

## Infants (<6 months)
Inpatient for WFL z <-3 (length >=45 cm), any oedema, visible severe wasting, too weak to suckle, or failure to gain weight. WFA z <-3 gives clinician referral (MAM tier, A2). Missing infant inputs give UNABLE_TO_CLASSIFY. MUAC ignored with a warning.

## Tests (`tests/rules`, `tests/safety`, 70 new, 196 total)
Boundaries for MUAC and WFL/H, oedema grades, every danger sign and complication, missing-information handling, HIV rule, implausible-value handling, 6-month boundary, infant rules, output contract, integration with Phase 1, and safety invariants.

## Not validated
No clinician review of the rules yet. Open items: I7-I11 in the decision log.
