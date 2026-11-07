# Changelog

## 0.3.0 - Phase 3
- `thanzi_screen.data`: seeded synthetic generator (50,000 random records plus 16 boundary records), recorded-error injection with ground-truth labels, missingness, leak-free stratified splits, validation, SHA-256 manifest, loader that refuses unverified or non-synthetic data.
- `scripts/generate_synthetic.py` CLI. Coarse `district` field (D33). MUAC is a placeholder assumption, not WHO MUAC-for-age.
- Labels for ML targets A (injected error) and B (review reasons) added. No deterioration target (C deferred).

## 0.2.0 - Phase 2
- CMAM 2016 classification and referral (`thanzi_screen.rules`): low risk, MAM, SAM-OTP, SAM-inpatient, SAM-assess, unable to classify.
- Rule registry with source, page and tag per rule; infant (<6 months) pathway; HIV-positive MAM rule.
- Weight <3.0 kg at 6 months or older triggers inpatient (R3 Table 5, D29). `AnthropometryResult.weight_kg` added.
- Safety tests: never less urgent than the most severe criterion; never OTP without complete information.

## 0.1.0 - Phase 1
- Anthropometric engine: WHO z-scores for weight-for-age, length/height-for-age, weight-for-length/height (0-59 months).
- WHO adjusted method for weight-based indicators beyond +/-3 SD, with flags.
- Checksummed reference tables, conversion script, 126 unit tests, including WHO worked examples.

## 0.0.0 - Phase 0
- Project scaffold, specification, reference register, decision log.
