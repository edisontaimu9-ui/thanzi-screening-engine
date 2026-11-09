# Module: growth monitoring, `thanzi_screen.growth` 

Compares a child with their own earlier visit and says so as an **advisory** flag. It never changes a classification, tier,
reason, review, ML flag or wording. Standard library only. Rule-based, so it also works in degraded mode.

Two checks, both from one optional `previous_measurement`:
1. **Weight gain** (`velocity.py`): average grams per day against the reference range in the ASPEN Paediatric and Neonatal Nutrition Support Handbook, Third Edition, 2024 (register R19, verified against the handbook).
2. **Trends** (`trend.py`): change in WHO z-score for weight-for-age, length/height-for-age and head
   circumference-for-age between the two visits.

`flagged` means "a person should look at feeding, illness and the measurements". It is not a diagnosis and not a finding under the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016
classification. Any flag also sets `review_suggested` with the note "A clinician should review this child's growth.".

## Why the caller sends the earlier visit
The engine stores nothing and accepts no child identifier, so it cannot look up history. The gateway or app holds the
child's records and sends one earlier visit as `previous_measurement`. Without it nothing changes.

## API
Request (optional): `"previous_measurement": {"age_days": 122, "weight_kg": 6.5, "length_height_cm": 62.3, "measure_position": "length", "hc_cm": 40.0}`.
Only `age_days` and `weight_kg` are required. `length_height_cm` needs `measure_position` (`length` or `height`, how that visit
was measured). Any other key (a name, a date of birth) is a 422. The earlier age must be before this visit. This visit's
length and position are already required on the under-5 route; its head circumference is the existing optional `hc_cm`.

Response (optional, both views): `growth_monitoring`. The weight-gain keys are as before (`assessed`, `reason`, `status`,
`flagged`, `weight_loss`, `interval_days`, `weight_change_g`, `rate_g_per_day`, `reference_low`, `reference_high`, `messages`,
`reference`, `advisory`), plus:
```json
{"reference_derived": false,
 "trends": {"length_height_for_age": {"indicator": "length_height_for_age", "assessed": true, "reason": null,
   "z_previous": -0.77, "z_current": -2.66, "z_change": -1.88, "direction": "fell", "lines_crossed": [-1, -2],
   "status_change": "below_minus2", "flagged": true,
   "messages": ["Length or height for age has fallen across z-score lines since the last visit. This may be a sign of slowing linear growth (stunting). A health worker should check feeding, illness and the measurements.",
                "The latest value is newly below -2 SD on the WHO Child Growth Standards, 2006."],
   "reference": "R4", "guide": "R21"}, "weight_for_age": {"...": "same shape"}},
 "review_suggested": true, "review_note": "A clinician should review this child's growth."}
```
That example is the WHO guide's own case study 2 (a boy, 4 and 18 months). Weight-for-age is normal there, length-for-age has
fallen from near the median to below -2.

`trends` has `weight_for_age` always, `length_height_for_age` only when both visits gave a length with its position, and
`head_circumference_for_age` only when both visits gave a head circumference. An indicator that is not assessed has
`assessed: false` and a `reason`.

## The rules
| Indicator | Flagged when | Source |
|---|---|---|
| Weight gain | below the ASPEN range for the ages in between (weight loss included). Above is reported, never flagged | R19 |
| Weight-for-age | z falls 1.0 SD or more, or newly falls below -2 or -3 | R5, R21 |
| Length/height-for-age | same | R4, R21 |
| Head circumference-for-age | z changes 1.0 SD or more, up or down. No single-value cut-off | R20, R21 |

A rise in weight or length is reported (`direction: rose`) and not flagged. A z-score of exactly -2.0 is not below -2.
`lines_crossed` lists the whole lines from -3 to +3 between the two values. The 1.0 SD is an engineering choice: the
guide says a line crossing a z-score line is a warning but gives no number of SD.

| Situation | Result |
|---|---|
| No `previous_measurement` | No `growth_monitoring` key. Response identical to before. |
| Interval under 28 days | Everything `interval_too_short`: "Compare again after at least 4 weeks." |
| A z-score outside the engine's limits | `implausible_measurement` for that indicator. Not flagged: a typing slip is not a trend. |
| Oedema on this visit | Weight-for-age trend `oedema_weight_unreliable`. Length and head still run. |
| Past 1856 days (all) or 1826 days (head) | `outside_reference_ages` |
| Girl aged 3 to 6 months | Weight gain uses the derived range 17 to 25 g/day; `reference_derived: true` and a message when below range |
| Earlier age not before this visit, a non-positive value | 422 `invalid_input`. Wrong types, a length without its position, unknown keys: 422 `invalid_request`, `missing_field`, `unknown_field`. |
| Preterm or corrected-age route | Not run. A warning says so. |
| Degraded mode (no ML models) | Still runs. |

Head circumference uses the weekly WHO table to day 91 and the monthly table after, with linear interpolation. The
earlier visit's length is converted by the engine's 0.7 cm rule if it was measured the other way for that age (tested equal to the engine).

## References
- Weight gain: `src/thanzi_screen/growth/aspen_weight_velocity.json` (R19), g per day. Bands (months): 0-1, 1-2, 2-3, 3-6, 6-9, 9-12,
  12-18, 18-24 (by sex), 2-<4 years and 4-7 years (not split by sex; only the part under 5 years is used). Girls 3 to 6 months is
  derived from the handbook's single value 21. Months are 30.4375 days. A test keeps an independent copy of the transcription.
- Trends: WHO z-score tables R5 (weight-for-age), R4 (length/height-for-age), R20 (head circumference, converted CSVs in
  `anthro/reference_tables/` with checksums in `MANIFEST.json`), and the technical guide R21.

Not used, and why: length and height velocity, rows for 7 years and over, the preterm monitoring rows; a separate
"flat line" rule; corrected-age trends.

## Design choices (reviewed by a dietitian)
- The 1.0 SD fall and the derived girls 3 to 6 month range.
- Head circumference plausibility limits of -5 to +5.
- The wording of the messages.
The feature is advisory and not validated on real children.

## Out of scope
Corrected-age trends (no source); preterm velocity per kg; single-value head circumference cut-offs; BMI-for-age and MUAC trends (no cited cut-offs or tables). Each can be added when a source is available. The gateway work needed to send `previous_measurement` is described in the [integration guide](../deployment/integration.md), section 6.

## Tests
`tests/growth/test_velocity.py`, `tests/growth/test_trend.py`, `tests/anthro/test_hc_tables.py`,
`tests/api/test_growth_monitoring.py`, `tests/api/test_growth_trends.py`.
Weight gain: reference matches the transcription; derived range recomputed from its neighbours; within, below, above; range ends
count as inside; weight loss; band blends; 28-day boundary; invalid input; 3000-case invariants.
Trends: constants and z-scores equal the anthro engine; head z checked against the published SD columns; the rule at exact
boundaries (-1.0, -0.99, -2.0, -2.01, -3.0); both directions for head size; the guide's Fadi case; which indicators appear;
oedema; ages past the tables; implausible values; 14 invalid inputs; 2000-case invariants; standard library only.
Tables: checksums, shape, published SD columns, interpolation, the weekly to monthly hand-over, end at 60 months.
API: result and wording; the rest of the response identical with and without it (both views); degraded mode; bad input with no
echoed values; preterm and corrected-age routes; HTTP and OpenAPI.
