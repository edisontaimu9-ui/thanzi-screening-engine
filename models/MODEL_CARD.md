# Model card: advisory recording-error flags

**Demonstration model trained on synthetic data only. Not validated on real children. Not for clinical deployment. Advisory flags only: it never changes a clinical classification.**

Version 0.4.0. Trained on synthetic dataset SHA-256 `2104b2c2a3734861...` (50016 rows), seed 0. Plain-Python models saved as JSON.

## Models
- `recording_error_lr.json`: logistic regression, flags a possible recording error (target A).
- `recording_field_tree.json`: shallow decision tree, suggests which field to recheck.
- `review_replica_diagnostic.json`: NOT production. Target B is a rules-based flag (`thanzi_screen.rules.review`); this model only measures how well ML copies it.

## Operating point (chosen on validation)
Threshold 0.1322. Target: at least 80% recall on errors the anthropometry flags miss, at most 10% of records flagged. Met on validation: **True**.

## Test results (synthetic data)
- ML flag: precision 75.8%, recall 97.2%, alert rate 4.8%, AUC 0.997.
- Anthropometry flags alone: precision 100.0%, recall 43.1%.
- Anthropometry flags or ML: recall 97.2%, alert rate 4.8%.
- Recall on errors the anthropometry flags miss (160 records): 95.0%.
- Field suggestion accuracy on error records: 99.6%.
- Boundary stress test: 15 false alarms in 16 records; 12 of them have an age that is an exact 6-month multiple (the boundary set uses 365 days), which the model treats as age heaping. A child legitimately aged exactly 12 months would be flagged the same way.
- B replica agreement with the rules: precision 85.0%, recall 79.0%.

## Recall by error type (test)
- age_heaping: ML 100.0%, Anthropometry flags 0.0%, either 100.0% (n=73).
- length_digit_transposition: ML 87.7%, Anthropometry flags 66.7%, either 87.7% (n=57).
- muac_unit_error: ML 100.0%, Anthropometry flags 0.0%, either 100.0% (n=67).
- weight_decimal_shift: ML 98.8%, Anthropometry flags 98.8%, either 98.8% (n=84).

## Limits
- Error types and rates are assumptions. Real recording errors are messier.
- Age heaping is caught here only because the synthetic injection rounds ages exactly to 6-month multiples. Real heaping is fuzzy and is a population pattern, so this result will not transfer.
- Synthetic districts carry no signal, so the district report checks the code, not real fairness. Fairness testing needs real data.
- Retrain when real prevalence figures (R9) and WHO MUAC tables (R8) are adopted for the synthetic data generator.
