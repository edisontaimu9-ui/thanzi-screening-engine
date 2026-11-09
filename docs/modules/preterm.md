# Module: preterm

Screens babies born preterm (under 37 weeks) or low birth weight (under 2500 g) with Fenton 2025 growth data and the Care of the Infant and Newborn (COIN), Malawi, 2017 rules, and hands them to the under-5 engine at 50 weeks post-menstrual age (PMA) on corrected age. Release candidate, **not validated**. Decision support only.

## Layout
```
src/thanzi_screen/preterm/
  engine.py              upstream preterm engine (screen, features, PretermInput). Logic not changed.
  preterm_rules.json     upstream rules data. Clinical values live here, including those tagged "proposed".
  fenton2025_lms.json    upstream data, UNMODIFIED. CC BY-NC-ND 4.0. Keep its meta block.
  routing_config.json    integration settings: routing thresholds, corrected-age end points, level map, unit guards.
  routing.py             route(age_days, ga_weeks, birth_weight_g) -> Route; the level map (tier_for).
  integration.py         request -> PretermInput, oedema rule, worker and audit response.
src/thanzi_screen/ml/preterm_features.py   ML feature row (features()), kept apart from ml/features.FEATURES.
```
Only standard library at run time. The upstream service's own `api.py` and `Dockerfile` are not used: this repository's API and image carry the engine.

## Routing
`POST /v1/screen` routes automatically from two optional fields, `gestational_age_weeks` and `birth_weight_g` (grams). Without them the request is screened exactly as before.

| Born | PMA (GA + chronological age) | Runs | Age given to the engine |
|---|---|---|---|
| under 37 weeks, or under 2500 g | under 50 weeks | preterm engine | chronological (Fenton uses PMA) |
| under 37 weeks | 50 weeks or more, chronological age under 36 months if GA under 32 weeks, under 24 months if GA 32 to under 37 (per the clinical guidelines) | under-5 engine | corrected: age_days - round((40 - GA) x 7) |
| under 37 weeks | 50 weeks or more, after the period above | under-5 engine | chronological |
| 37 weeks or more but under 2500 g | 50 weeks or more | under-5 engine | chronological: prematurity correction applies only to babies born preterm |
| neither | any | under-5 engine | chronological |
| under 2500 g, gestational age not given | any | under-5 engine, with a warning and `clinical_assessment.needed = true` | chronological. Gestational age is never assumed |
| under 37 weeks, birth weight not given | under 50 weeks | rejected, 422 | n/a |

Exactly 37 weeks and exactly 2500 g are not "under". PMA 50.00 weeks goes to the under-5 engine. The 50 comes from `preterm_rules.json` (`hand_over_to_under5_engine.at_pma_weeks`); the other thresholds from `routing_config.json`.
On the corrected-age route the under-5 engine runs unchanged on the corrected age, so every age-dependent criterion of the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 uses corrected age automatically: MUAC from 6 months, the infant (under 6 months) criteria, the WHO z-score tables. The thresholds themselves are not changed; a test checks the result equals the plain under-5 result at the corrected age. The response adds `route` and `birth_context`. The ML recording-error flag is not run there (models were trained on chronological ages).

## Level mapping (one table: `routing_config.json` -> `routing.tier_for`)
The under-5 engine's levels are its `tier` values. No new level was added.

| Preterm level | Under-5 `tier` | Note |
|---|---|---|
| routine | low_risk | |
| follow_up | none (null) | Kept as its own preterm disposition. The under-5 engine has no follow-up tier and it is not forced into mam or low_risk. `tier` is null and `tier_note` says to use `preterm_level`. Gateways must handle a null tier. |
| refer | mam | Same precedent as `INF.WFA_CLINICIAN` (infant referred to a clinician maps to the MAM tier, no programme). |
| urgent_refer | urgent | Only danger signs can produce this. |

`recheck` is not used by the preterm route. The preterm response has no `classification` from the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016: a preterm level is not one of its classes.

## Wording
In the worker view "failure to gain weight" (Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, Table 5) is shown as "faltering growth (not gaining weight)". Codes, rule ids and the audit view keep the original terms of the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016.

## Inputs: reused, not duplicated
| Preterm trigger | Read from |
|---|---|
| convulsions | `danger_signs: convulsions` |
| lethargic | `danger_signs: lethargy_not_alert` or `unconsciousness` |
| cannot feed | `danger_signs: unable_to_drink_or_breastfeed` or `too_weak_to_suckle: true` |
| hypoglycaemia not correcting | `complications: hypoglycaemia` (urgent: a listed medical complication, inpatient, Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, Table 5) or the explicit `hypoglycaemia_not_correcting`. `routing_config.json` `hypoglycaemia` can require the explicit field instead |
| dehydrated | `complications: severe_dehydration` (no milder grade exists) |
| sick | new `sick`, or any under-5 danger sign or complication |
| no weight gain | new `consecutive_days_gaining_weight`; if null and `failure_to_gain_weight` is true, 0 is used |
| bilious vomiting, apnoea, cyanosis, abdominal distension, blood in stool, feed intolerance | new `neonatal_danger_signs` list (null = not assessed). Kept out of the `DangerSign` list so no rule from the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, changes |
| apnoea in 7 days, unstable temperature, gastric aspirate, head circumference, birth length, birth head circumference | new optional fields |

Units: `weight_kg` is kilograms, `birth_weight_g` is grams. A swap is rejected, not converted. Sex is `male` or `female` on both routes. Age is whole days on both routes. `length_height_cm` and `measure_position` are optional only on the preterm route (no length z-score without a length; a length needs its position, and it must be `length`); every under-5 flow still requires them. `oedema` stays explicit and required. On the preterm route any oedema grade is `urgent_refer` (Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, Table 5: any oedema in an infant under 6 months, and +++ at any age, are inpatient criteria). Oedema is a clinical sign, not a growth measure, so "growth alone never gives urgent_refer" still holds. Grades are set per grade in `routing_config.json`.

## Rules that must not change (tests in `tests/preterm/`)
- No faltering-growth call from a single percentile. It uses z-score decline from birth (weight and length: mild 0.8 to 1.2, moderate above 1.2 to 2, severe 2 or more; head circumference: flag above 1, refer above 2), and only after 14 days of age.
- Growth alone never gives `urgent_refer`.
- "Faltering", never "failure", in the preterm output.
- Values tagged "proposed" or "needs clinician sign-off" are read from `preterm_rules.json` or `routing_config.json`.
- The urgent triggers are one list, `urgent_triggers.rules` in `preterm_rules.json`; `engine.py` reads it and tests check the rules and the config agree. The "not gaining" age is `growth_assessment.min_age_days`.

## Data licence
`fenton2025_lms.json`: Fenton 2025 growth chart data, Dr Tanis Fenton, **CC BY-NC-ND 4.0**: attribution required, non-commercial, no derivatives. The file is byte-identical to the upstream file (SHA-256 checked in a test) and is copied into the image. Every preterm response carries `data_attribution`. Commercial use needs the author's permission. Care of the Infant and Newborn (COIN), Malawi, 2017 is the Malawi Ministry of Health manual.

## Clinician sign-off items
1. The level map (follow_up has no under-5 tier) and how gateways treat a null tier.
2. The z-decline tiers and head-circumference limits (literature-based, not from the Care of the Infant and Newborn (COIN), Malawi, 2017).
3. The urgent triggers tagged [proposed] in `preterm_rules.json`: convulsions, apnoea now, cyanosis, hypoglycaemia not correcting, abdominal distension with blood or feed intolerance, cannot feed with dehydration or lethargy.
4. Corrected-age end point for GA 32 to under 37 weeks: 24 months, taken from the clinical guidelines.
5. The mapping of the other under-5 inputs to preterm triggers. Hypoglycaemia and oedema follow Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, Table 5 (see above).
6. Unit guards and plausible ranges in `routing_config.json`.
7. The engine's own output was checked against its tests only, not against clinical cases.

## ML
`ml/features.FEATURES` is unchanged, so saved models still load. `ml/preterm_features.py` exposes the engine's `features()` row (`ROW_COLUMNS`), `PRETERM_FEATURES` (row minus `rule_level`) and `preterm_vector` (NaN becomes 0.0 plus `*_missing`). `rule_level` is the rule engine's own level: it is never a label and not in the vector; `assert_valid_label` refuses it. No preterm model or preterm training data exists yet.
