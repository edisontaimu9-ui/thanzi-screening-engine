# Module: growth monitoring, `thanzi_screen.growth` (add-on, not a numbered phase)

Detects slow weight gain between two visits and says so as an **advisory** flag. It never changes a classification, tier,
reason, review, ML flag or wording (D9, D159). Standard library only. Rule-based, so it also works in degraded mode.
**Reference values are not yet verified** (I59).

## What it does
Given the child's sex, an earlier weight and age, and this visit's weight and age, it:
1. checks the interval is at least 28 days and both weights are plausible (D162);
2. works out the average gain in g per day;
3. finds the ASPEN reference range (R19) for the ages in between, averaged over the days spent in each age band;
4. returns `below_range`, `within_range` or `above_range`. Only `below_range` (which includes weight loss) is flagged.

`flagged` means "a person should look at feeding, illness and the measurements". It is not a diagnosis and not a CMAM
classification. The reference is a range for term infants and paediatric patients, so a low gain is a prompt, not a verdict.

## Why the caller sends the earlier visit
The engine stores nothing and accepts no child identifier (D25), so it cannot look up history. Hope's gateway or app holds the
child's records and sends one earlier visit as `previous_measurement` (D158). Without it nothing changes.

## API
Request (optional): `"previous_measurement": {"age_days": 274, "weight_kg": 8.5}`. Only those two keys. A date of birth, name or
any other key is a 422. The earlier age must be before this visit.

Response (optional, both views): `growth_monitoring`
```json
{"assessed": true, "reason": null, "status": "below_range", "flagged": true, "weight_loss": false,
 "interval_days": 31, "weight_change_g": 50.0, "rate_g_per_day": 1.61,
 "reference_low": 4.0, "reference_high": 12.0,
 "messages": ["Weight gain since the last visit is below the usual range for this age. This may be a sign of growth faltering. A health worker should check feeding, illness and the measurements."],
 "reference": "R19", "advisory": "Advisory only. It does not change the classification. A trained health worker decides."}
```
That example is a 10-month-old boy, healthy by every CMAM measure (`classification: low_risk`), who gained 50 g in 31 days.

When not assessed: `assessed: false`, `reason` is one of `interval_too_short`, `implausible_weight`, `reference_unverified`,
`outside_reference_ages`, `status` is null, `flagged` is false and `messages` explains in plain words.

| Situation | Result |
|---|---|
| No `previous_measurement` | No `growth_monitoring` key. Response identical to before. |
| Interval under 28 days | `interval_too_short`: "Compare again after at least 4 weeks." |
| A weight outside the engine's weight-for-age plausibility limits | `implausible_weight`. Not flagged: a typing slip is not growth faltering. |
| Girl aged 3 to 6 months (any part of the interval) | `reference_unverified` until the table is checked (I59). |
| Earlier age not before this visit, or weight not positive | 422 `invalid_input`. Wrong types or missing keys: 422 `invalid_request`, `missing_field`, `unknown_field`. |
| Preterm or corrected-age route | Not run. A warning says so. |
| Degraded mode (no ML models) | Still runs. |

## The reference (R19)
`src/thanzi_screen/growth/aspen_weight_velocity.json`, weight in g per day, from the ASPEN Paediatric and Neonatal Nutrition
Support Handbook, 3rd ed., "Reference normal growth velocity". Transcribed by hand from a screenshot Edison supplied on
2026-11-08 and **not checked against the book**. Bands (months): 0-1, 1-2, 2-3, 3-6, 6-9, 9-12, 12-18, 18-24 (by sex), 2-<4 years
and 4-7 years (not split by sex; only the part under 5 years is used). Girls 3 to 6 months is blank because the source reads
21-21. Months are 30.4375 days. A test keeps an independent copy of the transcription.

Not used, and why: length and height velocity, rows for 7 years and over, and the preterm monitoring rows (D160). Not in the
screenshot's scope here: macronutrient, protein and enteral feeding tables (point-of-care nutrition guidance, not growth
monitoring).

## Design choices that need clinical confirmation
- The 28-day minimum interval (I60). Weights read to 0.1 kg are noisy over short gaps.
- Averaging the range across band edges (D161). It is arithmetic on the published ranges, not a published rule.
- What a flag should trigger (I61).

## Not covered (I62)
Change in weight-for-age z-score across visits, length or height faltering and stunting trend, head circumference, preterm
velocity per kg. Each needs a cited definition and cut-off first.

## Tests (`tests/growth/test_velocity.py`, 39; `tests/api/test_growth_monitoring.py`, 67)
Reference file matches the transcription and is marked unverified; bands contiguous; suspect cell unused; plausibility limits
equal the engine's; within, below, above; range ends count as inside (floating-point safe); weight loss; blend across band edges
checked against an independent calculation; no sex split from 2 years; girls 3 to 6 months not assessed; 28-day boundary;
implausible and out-of-range cases; 12 kinds of invalid input; 3000-case invariants; stdlib-only and isolation (only
`api/service.py` imports it); package data. API: result and wording; absent without input; rest of the response identical with
and without it (both views, 32 combinations); low-risk child still flagged; degraded mode; no HIV leak; 15 bad inputs with no
echoed values; preterm and corrected-age warnings; HTTP round trip and 422s; OpenAPI.
