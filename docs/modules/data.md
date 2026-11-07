# Module: data (Phase 3)

Synthetic data pipeline for under-fives (0-59 months). Standard library only. Synthetic only: real data is refused.

## Run
```
python scripts/generate_synthetic.py                 # seed 42, 50,000 records, writes data/synthetic/
python scripts/generate_synthetic.py --seed 7 --n 1000 --out /tmp/syn
python scripts/generate_synthetic.py --config my_config.json
```
Outputs `synthetic_children.csv` (random records, then 16 boundary records) and `MANIFEST.json` (SHA-256, row counts, seed, full config, Python version). The CSV is git-ignored; regenerate it. The same seed, config and Python version give a byte-identical file.

```python
from thanzi_screen.data import GenConfig, generate, write_dataset, load_dataset
cfg = GenConfig(seed=42, n=50_000)
write_dataset(generate(cfg), cfg, "data/synthetic")
rows = load_dataset("data/synthetic/synthetic_children.csv")   # verifies manifest, checksum, synthetic marker
```

## Limits (read first)
- Parameters are placeholders (ASSUMPTION), not Malawi prevalence (D37). Clinical rates (appetite, danger signs, HIV and others) are invented for exercising the rules.
- MUAC is a linear placeholder tied to WFL/H z. It is not a WHO MUAC-for-age model (D38, R8 pending).
- Results show the engine and pipeline work. They say nothing about real clinical risk.

## How a record is made
1. Sex, a coarse district (28, equal weights, D43) and age in days (uniform 0-1856).
2. LHFA z then WFL/H z (correlation 0.2). WHO LMS tables from Phase 1 are inverted (with the WHO adjusted-z extension beyond +/-3) to get length or height (0.1 cm) and weight (0.01 kg).
3. MUAC from the placeholder model, 6-59 months only (D2). Oedema, appetite, danger signs, complications, HIV and infant items sampled with severity-dependent rates.
4. Missing values (MCAR) and injected recording errors (weight decimal shift, length digit transposition, MUAC unit error, age heaping).
5. The real Phase 1 and Phase 2 engine runs on the recorded values to produce z-scores, class, tier, programme and rules fired. Nothing is re-implemented.
6. Splits 70/15/15 stratified by class; boundary records get split `boundary`.

## Columns
Identification: `child_id` (random surrogate), `is_synthetic`, `record_type`, `split`, `district`. Recorded inputs: sex, age_days, measure_position, weight_kg, length_height_cm, muac_cm, oedema, appetite, danger_signs, complications, clinically_well_and_alert, hiv_positive and the three infant items. Encodings: tri-state `true`/`false`/`unknown`, blank = not applicable; sets `none`, `unknown` or `a;b`. Ground truth: `true_*` values and `injected_error` (ML target A). Engine outputs: `wfa_z`, `lhfa_z`, `wflh_z`, `cmam_class`, `tier`, `programme`, `rules_fired`. ML target B: `review_needed`, `review_reasons` (D40).

## Privacy
No names, dates of birth, facilities, communities or coordinates. Geography is district only. `validate_rows` rejects forbidden columns, non-synthetic rows, duplicates and out-of-range values. `load_dataset` refuses a missing manifest, checksum mismatch, a manifest that does not declare the data synthetic, or rows not marked synthetic.

## Tests (`tests/data`, 26)
Reproducibility and hash, manifest, validation, geography, z-scores recomputed by Phase 1 match sampled targets, labels equal fresh `classify`, sampled moments, every class exercised, boundary records, error and missingness rates, errors change values, review consistency, split leakage and stratification, loader refusals, config, CLI.

## Typical output (seed 42, 50,000 records, this environment)
low_risk 41,668; MAM 4,842; SAM inpatient 1,790; SAM OTP 1,030; unable to classify 554; SAM assess 132. About 3.7% of records carry an injected error; about 17% are flagged for review (many are MUAC placeholder discordance). Not a prevalence claim.
