# Module: ml and review flags

Advisory flags only. They never change a classification, tier, referral or warning. Pure Python, offline, models stored as JSON.

## What it flags
- **Target A, possible recording error (ML).** Logistic regression gives a probability. Above the threshold it raises a flag, and a shallow decision tree suggests the field to recheck: weight, length/height, MUAC or age.
- **Target B, review needed (rules).** `thanzi_screen.rules.review` is deterministic: unable to classify, missing assessment, implausible value, weight under 3 kg, MUAC versus WFL/H disagreement, MUAC within 0.2 cm of a cut-off, WFL/H within 0.1 z of a cut-off. Each reason has a code and a plain-language message.
- An ML replica of B (`models/review_replica_diagnostic.json`) is a diagnostic only, marked `production: false`.

## Use
```python
from thanzi_screen.ml import flag_record, load_models
from thanzi_screen.rules import ClinicalInputs

models = load_models()                      # reads models/ in the repo
f = flag_record("male", 300, 86.0, 70.0, "length", ClinicalInputs(muac_cm=13.5), models)
f.recording_error.flagged, f.recording_error.suggested_field, f.recording_error.messages
f.review.needed, f.review.reasons, f.review.messages
```
`flag_record` runs anthropometry and classification itself. `ClassificationResult` has no flag fields.

## Train
```
python scripts/generate_synthetic.py            # makes data/synthetic/ (git-ignored)
python scripts/train_models.py                  # writes models/*.json and models/MODEL_CARD.md
python scripts/compare_sklearn.py               # optional, dev-only; skips if scikit-learn is missing
```
Training refuses datasets without a valid manifest or not marked synthetic. Same dataset and seed give identical JSON.

## Features
Recorded values, z-scores and flags, cross-indicator gaps, "would a digit swap or 10x weight change fix it" checks, MUAC unit checks, distance of age to a 6-month multiple, missingness indicators, the classification. Never `true_*`, `injected_error`, `review_*`, `split`, `record_type`, `child_id` (a test enforces this).

## Results on synthetic data (seed 42 dataset, test split)
See `models/MODEL_CARD.md`. In short: ML recall 97% at a 4.8% alert rate against 43% recall for the anthropometry flags alone; 95% recall on errors the anthropometry flags miss; field suggestion 99.6% accurate. scikit-learn gave the same AUC (0.998) and field accuracy (99.6%).

## Limits
- Synthetic, clean, injected errors. Real performance is unknown. Not validated on real children, not for clinical deployment.
- Age heaping works here only because the injection rounds exactly. The same feature flags a child aged exactly 12 months.
- Fairness cannot be tested without real data.

## Tests (`tests/ml`)
Leakage guard, determinism, refusal of unverified data, operating point and quality floors, subgroup report, labels and model card, JSON round trip, inference on normal, erroneous and missing-input records, flags never alter a classification, review rules and their agreement with the synthetic-data labels, model code, shipped models.

## See also
Free-text note processing lives in `thanzi_screen.ml.nlp`: `docs/modules/nlp.md`.
Weight-gain monitoring between visits lives in `thanzi_screen.growth`: `docs/modules/growth.md`.
Small neural networks (training, inference, hardware-aware presets) live in `thanzi_screen.ml.dl`: `docs/modules/dl.md`.
