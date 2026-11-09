# Module: deep learning, `thanzi_screen.ml.dl` 

Small neural networks that train and run on modest hardware, beside the logistic and tree models and the NLP
module. Advisory only. They never change a classification, tier, referral or warning. Standard library only,
offline, deterministic. **Demonstration, not validated**.

## What it adds
- **`Network`** (`network.py`). Dense feed-forward network in plain Python: ReLU hidden layers, Adam, mini-batches,
  L2, optional dropout, class weights, early stopping on validation loss (best epoch kept). One sigmoid output
  (binary) or a softmax over `classes`. JSON in and out, never pickle. Weights are checked on load (shape, finite
  numbers, positive std). `top_signals` names the inputs whose removal (set to the training mean) moves the output
  most. No project imports, so it can be reused alone.
- **Presets and a parameter budget.** `tiny` (16), `small` (32-16), `base` (64-32) hidden units. A network over
  20,000 parameters is refused unless `max_params=` is raised on purpose. With the 36 features: tiny 609, small 1,729,
  base 4,481 parameters.
- **Hardware awareness (`hardware.py`).** `detect_hardware()` reads CPU count and available memory (None if the system
  hides it, as some Android builds do) and times a short loop. `recommend_preset()` picks the largest preset whose
  estimated training time fits a budget (default 15 minutes). The estimate is rough (aim: within 2x; measured here:
  estimate 495 s, real run 214 s with early stopping). Nothing from this module is written into model files or cards.
- **Training (`dl/train.py`, `scripts/train_deep.py`).** Same verified synthetic data, splits, operating-point rule and
  report as the logistic models, so numbers compare directly. Error flag (binary) plus a small multiclass network for the field to
  recheck. Writes `models/recording_error_mlp.json`, `models/recording_field_mlp.json`, `models/DL_MODEL_CARD.md`.
- **Inference (`dl/predict.py`).** `flag_record_deep(...)` returns the same `MlFlags` as `flag_record`. `compare_record(...)`
  runs the logistic and deep models on one record and reports both flags, whether they agree and the mean probability.
  `predict_batch` scores many rows.

## Use
```python
from thanzi_screen.ml import load_models
from thanzi_screen.ml.dl import compare_record, flag_record_deep, load_deep_models
from thanzi_screen.rules import ClinicalInputs

deep = load_deep_models()                   # reads models/ in the repo
f = flag_record_deep("male", 300, 86.0, 70.0, "length", ClinicalInputs(muac_cm=13.5), deep)
f.recording_error.flagged, f.recording_error.suggested_field, f.recording_error.top_signals

c = compare_record("male", 300, 86.0, 70.0, "length", ClinicalInputs(muac_cm=13.5), load_models(), deep)
c.agree, c.logistic.probability, c.deep.probability
```

## Train
```
python scripts/generate_synthetic.py                     # makes data/synthetic/ (git-ignored)
# The ml tests need only pytest: python -m pytest tests/ml -q
python scripts/train_deep.py                             # preset small, writes models/*_mlp.json and DL_MODEL_CARD.md
python scripts/train_deep.py --preset auto --budget 600  # picks a preset for this device
python scripts/train_deep.py --preset tiny --epochs 20   # fastest
```
Training refuses datasets without a valid manifest or not marked synthetic. Same dataset, seed and settings give
identical JSON (a test checks the bytes). Run `train_models.py` first if you want the card to include the logistic
comparison; it is added only when the logistic model was trained on the same dataset.

## Results on synthetic data (seed 0, default dataset, test split, preset small)
See `models/DL_MODEL_CARD.md`. Deep flag: recall 98.6%, alert rate 4.8%, AUC 0.997, recall on errors the anthropometry flags miss
97.5%, field suggestion 100%. Logistic: recall 97.2%, alert rate 4.8%, AUC 0.997, 95.0%, 99.6%. The gap is a few
records out of 281 on one seed. Treat the two as equal. The synthetic task is close to linearly separable, so extra
depth has little to gain here, and this says nothing about real data.

## In the API
`ml_flags.deep_recording_error` has the same shape as `recording_error` (`flagged`, `suggested_field`, `messages`;
`probability` in the audit view only). It is absent when the deep models are not loaded, in degraded mode and on the
corrected-age route. `GET /version` adds `deep_model_version`. The classification, tier, reasons, review and wording are
identical with and without it (tested on both views). The explanation layer still describes the logistic flag only.
If the two flags disagree, both are shown and a person decides.

## Rules it keeps
- **Advisory only.** A test checks that flags never change a classification.
- **Switched on, beside the logistic flag.** `POST /v1/screen` returns `ml_flags.deep_recording_error` next to
  `recording_error`. Both model files carry `production: true`. Only `api/app.py` and `api/service.py` import the
  package; the rules, anthropometry, explanation and preterm code do not (AST test). Switch off with
  `THANZI_DEEP_ENABLED=0`. A failure in it never touches the screening result (tested).
- **No new packages.** `dependencies` stays empty and no extra is added (a test asserts it). scikit-learn, numpy
  and PyTorch are not needed and not used. No pickle.
- **Leak-free.** Uses the logistic model's `FEATURES` and the same leakage guard. Never `true_*`, `injected_error`,
  `review_*`, `split`, `record_type` or `child_id`.
- **Synthetic only.** Training reads only a verified synthetic dataset.

## Limits
- Synthetic, clean, injected errors. Real performance is unknown. Not validated on real children, not for clinical
  deployment.
- Pure Python is slow. About 3.5 minutes for the small preset on one core here. Low-powered devices may take several times longer.
  It is not for large data or large models. If that is ever needed, a numpy or PyTorch path would be a separate, reviewed
  change.
- A network is harder to audit than the logistic model. `top_signals` is an occlusion check, not a full explanation, and
  it is not connected to the explanation layer.
- The age-heaping result depends on the synthetic injection, as for the logistic model.
- Text: there is no deep text model. The NLP module stays rule-based because no authorised note data exists.

## Tests (`tests/ml/test_dl.py`, `tests/api/test_deep_flag.py`)
API tests: flag beside the logistic flag, probability audit-only, rest of the response identical with and without it (both
views, five records), absent without models and in degraded mode, a failing model does not touch screening and logs the
type only, no HIV information, corrected-age route, version field, loaded by default over HTTP, switch-off values, missing
and mismatched files leave `/health` ok, OpenAPI documents the fields.

Tests in `test_dl.py`:
Learns a rule a linear model cannot (XOR); multiclass; loss falls and early stopping keeps the best epoch; class
weights; dropout deterministic and off at inference; determinism and seed effect; JSON round trip; parameter budget;
ten malformed-file cases; input and mode guards; extreme inputs stay finite; `top_signals`; batch; hardware detection and
preset choice; hardware facts absent from artifacts; deterministic training bytes; refusal of unverified data; labels,
card and baseline comparison (and its skip on other data); quality floors; inference on normal, erroneous and missing
records; classification unchanged; `compare_record`; load refuses mismatched files; shipped models load; isolation in
both directions; standard library only; dependencies stay empty.
