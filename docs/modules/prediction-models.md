# Prediction module: model comparison and calibration

**Status: Phase 3. Compares and calibrates three model families. Export, strata, explanations and the model card are Phase 4: see
`prediction-export.md`. Not clinically validated, not for clinical use.** On simulated data the numbers only show that the pipeline works.

Code: `thanzi_screen.prediction.evaluate` (standard library), `candidates`, `compare`; runner `scripts/train_prediction.py`.
Training needs the `train` extra (numpy, scikit-learn, XGBoost), on the development machine only. The service never imports
them, and importing `thanzi_screen.prediction` loads none of them (tested).

```bash
python scripts/simulate_longitudinal.py                       # simulated data, git-ignored
python scripts/train_prediction.py --allow-simulated          # models/prediction_sim/results.json and REPORT.md
```

## Candidates

| Name | Setting (fixed, not tuned on test data) |
|---|---|
| Logistic regression | L2, C 0.5. The reference model. |
| Random forest | 300 trees, depth 6, at least 50 rows per leaf, square-root features. |
| XGBoost | 300 trees, depth 3, rate 0.05, 80% rows and columns, min child weight 20, lambda 5, **monotone constraints** from the feature registry (a lower z-score or MUAC never lowers the risk). |
| Best single feature | The one column with the best AUROC on **training** rows, signed by its training direction. A yardstick, not a model. |

Classes are **not** reweighted, so probabilities stay on the real scale and calibration is a fair question.

## Method (the order is fixed so the test split cannot steer a choice)

1. Labels and child-level splits come from Phase 2. The preprocessor is fitted on training rows only.
2. Candidates are fitted on training rows. Rows with a gap never seen in training are counted, not imputed.
3. **Platt calibration** is fitted on validation rows. A slope that is not positive is refused (it would reverse the order).
4. **Selection.** Logistic regression stays unless a challenger gains at least 0.01 AUROC on validation **and** the paired
   child-level bootstrap interval of the gain excludes zero. The simpler model wins ties.
5. **Alert thresholds** for 10% and 20% alert rates are fixed on validation rows.
6. **Test rows are read once**, to report: AUROC, AUPRC, Brier and its skill over the training prevalence, calibration slope,
   intercept and expected calibration error before and after Platt, deciles, paired AUROC differences against logistic
   regression and against the baseline, sensitivity, PPV and net benefit at the fixed thresholds, and subgroup tables (age
   band, sex, district) for the selected model. Small subgroups are shown and marked.

`fit_stage` never receives test rows, and a test confirms that flipping every test label changes nothing chosen before the test
step. A target with fewer than 30 events in any split is reported as **not trained** with the reason.

**Intervals resample children, not rows.** A child contributes several index visits that are not independent, so a row
bootstrap would give intervals that are too narrow (tested).

## Loss to follow-up check

`followup_balance` compares index visits that have a label with those lost (no visit in the 28 to 180 day window) on age,
WHZ, MUAC, wealth quintile, food insecurity and number of prior visits, as standardised differences. It is a warning light,
not a correction. The last visits of every child are unlabelled by construction, so differences in age and number of prior
visits are expected. A difference in wealth, WHZ or MUAC would mean the labelled children are not a fair sample.

## Example run (SIMULATED, 6,000 children, default seeds, 300 bootstrap resamples)

Test AUROC with 95% child-level interval. The simulator's associations are assumptions, so this says nothing about real children.

| Target (test events) | Logistic regression | Random forest | XGBoost | Best single feature | Selected |
|---|---|---|---|---|---|
| future_wasting (539) | 0.847 (0.828 to 0.869) | 0.837 | 0.847 | 0.809 (`waz`) | Logistic regression |
| future_sam (72) | 0.813 (0.729 to 0.871) | 0.852 | 0.781 | 0.814 (`whz`) | Logistic regression |
| future_faltering (793) | 0.782 (0.765 to 0.797) | 0.761 | 0.744 | 0.658 (`whz`) | Logistic regression |

What to take from it:

- Nothing cleared the selection rule, so the simplest model is kept for every target. The simulator's risk is close to
  additive, which favours a linear model. Real data may differ.
- For future SAM the intervals are wide and overlap completely. The random forest looks best on the test split, but it did not
  pass the rule on validation (38 events), and the test split must not be used to pick it after the fact.
- Random forest probabilities are poorly calibrated before Platt (slope 1.7 and 2.1 for wasting and faltering). Calibration
  fixes the slope but not the weaker ranking.
- The `future_faltering` baseline is `whz` with **higher** riskier. That is regression to the mean in the simulator, not a
  clinical finding. It is why the baseline is chosen on training data and not assumed.
- At a 10% alert rate for future SAM, sensitivity is about 0.58 and PPV about 0.09. Rare outcomes give low PPV whatever the model.

## Limits

- This step exports no model file. Export, risk strata, explanations and the model card are Phase 4 (`prediction-export.md`). No
  acceptance thresholds or clinical sign-off exist. Results are marked `clinical_use: false`.
- Fixed settings were not tuned. A tuning step needs its own nested validation, to be agreed before real data.
- Platt scaling on a small validation set is noisy (future SAM has 38 validation events). Slope and intercept before and after are
  both reported so this is visible.
- Subgroup fairness numbers are descriptive. Small subgroups are flagged, not corrected.
- The 28 to 180 day horizon and the faltering definition are still engineering choices for clinical reviewers.

## Added in Phase 4

The test report now carries a `strata` block for the selected model (cut-offs fixed on validation children at the 10% and 20% alert rates,
observed event rate per stratum on test children). It is report-only and changes no choice. `compare.run_target_with_state` returns the fitted
state for the export step; `run_target` is unchanged for callers.
