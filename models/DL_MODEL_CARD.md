# Model card: deep learning advisory flags

**Demonstration deep models trained on synthetic data only. Not validated on real children. Not for clinical deployment. Advisory flags only: they never change a clinical classification.**

Version 0.1.0. Trained on synthetic dataset SHA-256 `2104b2c2a3734861...` (50016 rows), seed 0. Plain-Python networks saved as JSON. Runs in the API as a second advisory flag beside the logistic flag (`production` is true; switch off with THANZI_DEEP_ENABLED=0). Same status as the logistic model: synthetic data only.

## Models
- `recording_error_mlp.json`: dense network 36-32-16-1 (1729 parameters), ReLU, sigmoid output, flags a possible recording error (target A).
- `recording_field_mlp.json`: dense network 36-16-4 (660 parameters), softmax output, suggests which field to recheck.

## Training
Adam, learning rate 0.003, dropout 0.0, up to 40 epochs, early stopping on validation loss (patience 6). Error flag: 18 epochs run, best epoch 12. Field model: 40 epochs run, best epoch 38.

## Operating point (chosen on validation, same rule as the logistic model)
Threshold 0.1477. Target: at least 80% recall on errors the anthropometry flags miss, at most 10% of records flagged. Met on validation: **True**.

## Test results (synthetic data)
- Deep flag: precision 76.5%, recall 98.6%, alert rate 4.8%, AUC 0.997.
- Anthropometry flags alone: precision 100.0%, recall 43.1%.
- Anthropometry flags or deep flag: recall 98.6%, alert rate 4.8%.
- Recall on errors the anthropometry flags miss (160 records): 97.5%.
- Field suggestion accuracy on error records: 100.0%.
- Boundary stress test: 15 false alarms in 16 records; 12 of them have an age that is an exact 6-month multiple.

## Against the logistic model (same dataset, same test split)
- Logistic: precision 75.8%, recall 97.2%, alert rate 4.8%, AUC 0.997, recall on errors the anthropometry flags miss 95.0%.
- Deep: precision 76.5%, recall 98.6%, alert rate 4.8%, AUC 0.997, recall on errors the anthropometry flags miss 97.5%.

## Recall by error type (test)
- age_heaping: deep 100.0%, Anthropometry flags 0.0%, either 100.0% (n=73).
- length_digit_transposition: deep 94.7%, Anthropometry flags 66.7%, either 94.7% (n=57).
- muac_unit_error: deep 100.0%, Anthropometry flags 0.0%, either 100.0% (n=67).
- weight_decimal_shift: deep 98.8%, Anthropometry flags 98.8%, either 98.8% (n=84).

## Limits
- Same synthetic data and assumed error types as the logistic model. Real recording errors are messier, so these numbers say little about real use.
- The synthetic task is nearly linearly separable, so a deeper network has little to gain here. Any gap to the logistic model on this data is not evidence about real data.
- Age heaping is caught only because the synthetic injection rounds ages exactly. The same artefact applies here.
- Fairness cannot be tested without real data. Neural networks are harder to audit than the logistic model; `top_signals` is an occlusion check, not a full explanation.
- Retrain when real prevalence figures (R9) and WHO MUAC tables (R8) are adopted for the synthetic data generator.
