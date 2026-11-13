# Prediction module: model export, risk strata, explanations and model card

**Status: Phase 4. Exports the selected model for each target as one plain JSON file the service can run without scikit-learn,
XGBoost or numpy. Not clinically validated. Models trained on simulated data are marked `clinical_use: false` and are refused by
the loader unless simulated models are explicitly allowed.**

Code (all standard library): `thanzi_screen.prediction.model` (the file and its checks), `predict` (one child), `explain`
(contributions and plain-language drivers), `trees` (tree evaluation and exact TreeSHAP). Development-machine tools: `export`
(fitted library object to JSON; it imports XGBoost only inside the one function that needs it), `card` (model card), and the runner
`scripts/export_prediction.py`. Importing `thanzi_screen.prediction` loads no training library and no screening module (tested).

```bash
python scripts/simulate_longitudinal.py
python scripts/export_prediction.py --allow-simulated      # models/prediction_sim/<target>.json, MODEL_CARD.md, REPORT.md, results.json
```

The script runs the Phase 3 comparison in the same fixed order (the test split is read once, to report), then exports only the
**selected** model of each trained target. A target reported as "not trained" is not exported. Output is deterministic: the same
data and seed give identical files (tested).

## The model file (`thanzi-prediction-model/1`)

One file per target holds everything needed to score a child and to refuse to:

| Part | Content |
|---|---|
| `preprocessor` | Training medians, winsorising limits, means, spreads and which features get a "not recorded" flag. Columns follow the canonical feature order, never the key order of the JSON (a bug this export found, now tested). |
| `model` | Logistic regression (coefficients on the preprocessed columns plus their training means), a random forest (`rf_prob`) or XGBoost (`gbm_logit`) as plain trees with covers. JSON only, never pickle. |
| `calibration` | Platt slope and intercept, fitted on validation children. A slope that is not positive is refused. |
| `strata` | Calibrated-probability cut-offs for `elevated` and `high`, fixed on validation children at the 20% and 10% alert rates. |
| `eligibility` | Age range, 6 to under 60 months. |
| `safeguards` | `max_missing_features`: the most inputs ever missing in a training row. A record only: it no longer stops a score. |
| `pathway` | Optional. `name`, `groups`, `required_features` (must be inputs of the model) and `history_withheld_pct`. |
| `target`, `provenance`, `clinical_use`, `dataset_sha256`, `seed`, `metrics`, `governance`, `acceptance` | What it predicts, where the data came from and what was approved. |

The loader fails closed. It refuses a file with a missing or malformed part, non-finite numbers, columns that do not match the
preprocessor, a tree deeper than 8 or covers that do not add up, or a file over 50 MB. It refuses a **simulated** model unless the
caller allows it, and a simulated model can never be marked for clinical use. A **real-data** model is refused without ethics,
data-agreement and clinical sign-off references **and** acceptance thresholds that were set in advance and passed. The export
script refuses to write real-data files without `--clinical-signoff` and an `--acceptance` file, and writes nothing in that case.

**Parity.** Before a file is written, the script loads it back through the service's own loader (from the same sorted-key JSON the
file will hold) and compares it with the training library on validation rows. A difference above 1e-5 stops the export. Tests repeat
the check for logistic regression, random forest and XGBoost on separate rows, and check that TreeSHAP contributions add up.

## Risk strata

Two strata, `elevated` (calibrated probability at or above the 20%-alert-rate cut-off) and `high` (10%). **There is no "low
risk" stratum.** A child under the lower cut-off gets no message at all, because the model cannot say a child is well. The test
report adds a strata table: children, events, observed event rate and share of all events per stratum, with the cut-offs fixed on
validation children and the rates observed on test children.

Example (SIMULATED, 6,000 children, test split):

| Target | Stratum | Children | Event rate | Share of all events |
|---|---|---|---|---|
| future_wasting | high / elevated / not flagged | 12.3% / 11.0% / 76.6% | 52.8% / 34.6% / 7.8% | 39.9% / 23.4% / 36.7% |
| future_sam | high / elevated / not flagged | 12.4% / 11.4% / 76.2% | 9.2% / 2.2% / 0.8% | 58.3% / 12.5% / 29.2% |
| future_faltering | high / elevated / not flagged | 8.4% / 10.0% / 81.6% | 60.7% / 45.1% / 14.7% | 23.6% / 20.8% / 55.6% |

What to take from it:

- The strata separate (event rate rises with stratum) but the "not flagged" group still holds 29% to 56% of the events. A rare
  outcome and a model with this discrimination cannot do better. That is why a flag never means "well" when absent.
- The share flagged on test children is not exactly the 10% and 20% fixed on validation. The cut-offs travel; the alert rate does
  not. Monitor it after any rollout.
- The `future_sam` cut-offs are small probabilities (about 0.017 and 0.026) because the outcome is rare. The wording says "higher than
  usual", not a percentage.
- The simulator's associations are assumptions. None of this says anything about real children.

## Safeguards for one child (`predict.assess_child`)

Each ends in a stable "not scored" code (`NOT_SCORED`), never a guess, and the function never raises. It logs the type of a failure,
never its message or the child's data.

1. Age outside the model's range: `age_outside_model_range`.
2. An input essential to the model's pathway is missing: `essential_input_unavailable`. The pathway minimum is `pathway.required_features` in the file (default: age, sex, weight-, height- and weight-for-height z-scores, oedema). Other empty inputs do not stop a score.
3. A gap never seen in training: `gap_never_seen_in_training` (the median is not used as a stand-in for "typical").
4. A record that cannot be turned into inputs: `invalid_input`. Any other failure: `model_error`.

Inputs come from `build_features`, which reads only visits up to and including the index visit (tested by changing every later
visit) and never uses the CMAM classification, tier or referral. The result can only add concern. It never changes a classification,
tier, referral or warning, and carries `non_clinical: true` for a simulated model.

## Explanations

Contributions are exact: baseline plus the sum of contributions equals the raw model output (a logit for logistic regression and
XGBoost, a probability for the random forest). Logistic contributions are measured against the training mean of each column. Tree
contributions use exact path-dependent TreeSHAP. A feature's value column and its "not recorded" flag are added together, so a gap
that raises the estimate is reported as "not recorded". Calibration is a monotone rescaling, so it does not change the order of the
drivers.

The bedside result shows up to three **drivers that raise** the estimate, in plain language ("weight-for-height z-score -1.2", "fever in
the last 2 weeks"). They say what contributed to a number, not what caused an outcome. Sex is kept in the audit list but never offered
as a bedside reason. `audit=True` returns every feature, its value and its contribution for reviewers.

`trees.py` is a copy of `thanzi_screen.ml.risk.trees`. The prediction module never imports `thanzi_screen.ml` (tested, as in Phase 2),
so reuse is by copy. A test checks that both give identical predictions and identical SHAP values on random trees.

## Model card

`MODEL_CARD.md` is written from `results.json` and the exported files, so every number on it was produced by the pipeline: what
the model does and does not do, split sizes, test AUROC with child-level intervals against the best single feature, calibration,
strata, loss-to-follow-up check, subgroup tables (age band, sex, district) and the export parity.

## Limits

- No acceptance thresholds, clinical sign-off or ethics approval exist, so nothing is approved for clinical use. A model trained on
  real data needs all three in the file or the service refuses it.
- The service loads exported files (`THANZI_PREDICTION_ENABLED=1`, `THANZI_PREDICTION_MODEL` = one file, a folder of them, or a
  comma-separated list) and adds one `ml_prediction` summary to `/v1/screen` on the plain under-5 route. Each model predicts one target; the
  summary consolidates them (`prediction/consolidate.py`). A file that is refused is skipped and `/v1/about` says `degraded`; none usable means
  no block. The block never changes the classification, tier or referral, and it is off by default.
- **Consolidation rules:** escalate only and no low-risk label; one result per target (where a target has several models, for example a full and
  an anthropometric pathway, the first that could be scored is used, and files with the plainest name, the full pathway, are tried first); one
  sentence for the worker, most severe stratum first, then `future_sam`, `future_wasting`, `future_faltering`; up to three distinct drivers;
  every target that could not be scored is listed with its reason; the consolidation never receives the classification, so it cannot change it.
  The worker view carries the summary only. The audit view adds each model's own result under `models`.
- The request carries no clinical history or feeding questions, so those inputs are reported `not_assessed` in the block's `inputs`, never filled
  in. Empty inputs that cannot exist (no earlier visit, deworming under 12 months, a first birth) are `not_applicable`. An earlier visit that
  is not valid and comparable (no length or height with its position, or under 14 days earlier) is not used and its inputs are `unavailable`.
- **Pathways (Phase 7).** `scripts/export_prediction.py --pathway anthropometric` trains and exports a model from measurements only (this visit and
  earlier visits). Clinical history, feeding, birth, maternal and household inputs are not part of it, so a request that leaves them empty is
  scored and they are reported `not_assessed`, never filled in. A fixed, repeatable 30% of rows have earlier visits withheld in training, so a
  first visit is scored from what the model learned about "no earlier visit". The run reports test AUROC with and without an earlier visit
  (`pathway_check` in `results.json`, and the model card). Files are named `<target>.anthropometric.json`. A model file without a `pathway`
  part is the `full` pathway and still needs every input it always saw in training (`gap_never_seen_in_training`).
- The loss-to-follow-up check cannot compare household inputs for a pathway that does not use them.
- The report package does not show the block yet. That wiring needs a clinical decision on wording and is not part of Phase 5.
- The strata are defined by alert rate on validation children. They are relative, not absolute, and must be monitored after rollout.
- Fixed settings were not tuned. Tuning would need its own nested validation, agreed before real data.
- The 28 to 180 day horizon and the faltering definition are still engineering choices for clinical reviewers.
- The age range (6 to under 60 months) and the missing-input limit are engineering choices, set from the training data and the
  simulator's design. Clinical reviewers should confirm them.
- Subgroup numbers are descriptive. Small groups are flagged, not corrected. Fairness needs a real evaluation, not a simulated one.
