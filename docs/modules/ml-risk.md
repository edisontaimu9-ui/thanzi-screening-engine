# Advisory clinical risk model

**Status: pipeline built and tested on simulated outcomes only. Not validated. Not for clinical use.**

The rules (Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016) stay authoritative. This module adds a
data-driven second opinion: an estimate of the chance of a later adverse outcome, used only to suggest closer follow-up.

## Design

1. Rules classify. The recording-error flags run. A suspected recording error means the child is not risk-scored.
2. `risk_features` builds 15 features from values the API already accepts (z-scores, MUAC, oedema, appetite, danger signs,
   complications, age, sex, weight change since a previous visit). The rule classification is not a feature.
3. The model gives a raw probability, Platt calibration (positive slope, so order is kept) gives the calibrated probability,
   and a threshold chosen on validation data for a target alert rate decides "elevated".
4. Escalate only: the block adds a concern and up to three plain-language reasons. When the model sees nothing extra, `elevated`
   is false and there is no message. That is never reassurance.

Not scored, with a stable reason code: age outside 6 to 59 months, MUAC missing, z-scores not assessable, suspected recording
error, recording-error check unavailable, invalid input, model error. Nothing is imputed as normal. Not run on the preterm or
corrected-age routes.

## Safety properties (tested)

- Classification, tier, referral, programme, reasons, warnings and `ml_flags` are identical with the block on or off.
- A failing model logs the error type only and returns `model_error`; screening continues.
- Off unless `THANZI_RISK_ENABLED=1`. A missing or refused model never degrades `/health`.
- Simulated models: `provenance: simulated`, `clinical_use: false`, `non_clinical: true` in every response, refused unless
  `THANZI_RISK_ALLOW_SIMULATED=1`.
- Real models: refused without ethics, data agreement and clinical sign-off references, and a passed acceptance check whose
  thresholds were set before the test set was opened.
- Worker view carries no probability. Audit view carries the calibrated probability and the exact per-feature contributions.
- Tree models are trained with monotone constraints (lower z-score or MUAC never lowers risk) and checked against the library
  (parity under 1e-5). Explanations add up exactly (checked at training time).

## Models and explanations

| Kind | Runtime | Explanation |
|---|---|---|
| `logistic` | plain Python | exact contributions in logit units |
| `gbm_logit` (XGBoost) | plain-Python tree evaluator | exact TreeSHAP, logit units |
| `rf_prob` (random forest) | plain-Python tree evaluator | exact TreeSHAP, probability units |

Logistic regression is the default. A challenger replaces it only if its validation AUROC gain is at least 0.01 and the paired
bootstrap interval of the gain excludes zero. Trees are limited to depth 8 and 500 trees, and every node needs a positive cover.

## Data

`ml/risk/data.py` defines the schema the government dataset must be mapped into: one row per child visit with a later outcome,
pseudonymous child ID (splitting only), district and period (fairness checks only), the API's input fields, an optional previous
weight, and a 0/1 outcome. No names, dates of birth, contacts, fine geography or facility names. The manifest must declare
`provenance: real`, `ethics_ref`, `data_agreement_ref`, `extraction_description`, `period_covered` and `deidentified: true`.
The outcome definition (target, window, handling of loss to follow-up) must be agreed with clinical reviewers before training.

## Workflow

```
python scripts/simulate_risk_outcomes.py                      # simulated dataset (git-ignored)
python scripts/train_risk.py --allow-simulated --lodo         # models/risk_sim/ and its model card
python scripts/train_risk.py --data <real>/risk_dataset.csv --out models/risk \
    --clinical-signoff REF --min-auroc-lower X --min-sensitivity Y --slope-range LOW HIGH
```

Random forest and XGBoost training needs scikit-learn and XGBoost on the development machine only. Logistic regression trains in
plain Python. Same dataset and seed give identical files. The model card reports the split, selection, operating point, test
metrics with intervals, comparison with the rules alone, calibration, decision curve, subgroups and leave-one-district-out results.

## Before any real use

Real data audit and target definition, ethics and data-sharing approval, acceptance thresholds agreed in advance, a silent
shadow period (outcome joining happens on the integrator side, because this service is stateless), clinical sign-off, a check of
regulatory status for decision-support software, and drift and calibration monitoring after release.
