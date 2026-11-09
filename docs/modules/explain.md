# Module: explain

Plain-language and audit explanations of the classification and the advisory flags. They describe. They never change a classification, tier, referral, warning or flag. Pure Python, offline.

## Use
```python
from thanzi_screen.explain import explain
from thanzi_screen.ml import load_models
from thanzi_screen.rules import ClinicalInputs

e = explain("male", 400, 8.0, 72.0, "length", ClinicalInputs(muac_cm=11.4), load_models())
e.summary                       # worker view, 2-3 lines
e.classification_trace          # rules fired (source, page, tag), criteria vs cut-offs, margins, reasons, warnings
e.flag_trace                    # ML probability, signed contributions, tree path, suggested field
e.review_trace                  # each review reason with its evidence
e.to_json(indent=2)             # whole object, JSON-serialisable
```
`explain_parts(anthro, result, clinical, flags, features, models)` explains outputs you already computed. `explain` runs the whole pipeline itself.

Try it: `python scripts/explain_demo.py --audit`

## Worker summary
1. Class phrase plus up to 3 deciding reasons, or what is missing or must be rechecked.
2. The action (referral wording without the placeholder prefix).
3. ML recording check and review reason, if any. Omitted otherwise.

Wording is advisory: "meets the criterion in the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 for...", never "has...". HIV wording never appears here.

## Audit trace
- **Classification:** `rules` come straight from `ClassificationResult.rules_fired`. `criteria` list each value against the same cut-offs the rules use (imported from `rules_v2016`), with the nearest cut-off and the margin (value minus cut-off). A value on a cut-off counts as the less severe side.
- **ML flag:** logistic contributions are `coef * (x - mean) / std`, so `bias + sum(contributions)` equals the logit exactly and `sigmoid(logit)` equals the flag probability. The tree path records each split. Contributions are not causal; correlated features share credit.
- **Review:** reason codes come from `rules.review.review`. The explanation adds the value, cut-off and margin behind each code. It never adds or removes a reason.
- **Audit notes:** the HIV-input note lives here only.

## What is not claimed
- The ML explanation says why the model raised a flag, not what the error is. Models are trained on synthetic data only.
- An exact-6-month age gets flagged and explained as "may be rounded or guessed; ignore if the date of birth is known".
- No counterfactuals: the engine never tells a worker which value would change the class.
- Wording is a draft pending clinical review. `ClassificationResult.referral_text` still holds HIV wording for rule MAM.HIV_OTP; use the summary, not raw `referral_text`, in the worker view.

## Message catalogue
`explain/messages.py`: one text per rule id, classification reason code, review code and ML feature. Tests fail if any rule, reason code, review code or feature lacks a message. English only for now.

## Tests
`tests/explain/test_explain.py`: catalogue completeness, exact logit identity, tree path equals the model's leaf, trace equals `rules_fired` on 1,216 generated records, margins at MUAC 11.4/11.5/12.4/12.5 and z near -3/-2, no change to results, review reasons equal `review()`, summary shape and safety wording, HIV wording audit-only, missing-assessment cases, determinism, JSON round trip.
