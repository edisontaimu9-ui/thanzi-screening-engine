# Phase 5 specification: explainability

Status: DRAFT. Waiting for Edison's answers to Q1-Q7. Nothing implemented.

## Objective
For every screening result, explain in plain language why the engine said what it said, and why an advisory flag was raised. Two audiences: the health worker at the point of care (short, no model terms) and the reviewer or auditor (full trace).

## Hard rules
- Explanations describe. They never change a classification, tier, referral, warning or flag (D9).
- Faithful: every explanation is derived from the same computation that produced the result. No second model, no post-hoc guess.
- Advisory language only: "meets the CMAM criterion for X", never "the child has X". Decision support, not diagnosis.
- Stable codes for every message so the team can translate. Wording ownership follows D34.
- Pure Python, standard library only, offline. No SHAP or LIME.

## Honest limits
- The ML explanation says why the model flagged a record, not what the actual error is. The model was trained on synthetic errors only (D41, D55).
- Linear contributions are exact for the logistic model but correlated features share credit. They are not causal.
- Age-near-6-month-multiple will also flag children truly aged exactly 12 months (D54, I16). The explanation must say so, so the worker can dismiss it.
- Explanation text quality for real users is untested. Needs clinician and health-worker review (Maria Talimire, team) before any use.

## Resources
No new external sources. Uses Phase 1-4 outputs and the rule registry (source and page per rule, R3 CMAM 2016).

## Deliverables
1. `src/thanzi_screen/explain/`
   - `trace.py`: classification trace. Rules fired (id, source, page), inputs used, each value against its cut-off, margin to the nearest cut-off.
   - `ml_explain.py`: logistic model signed per-feature contributions (coefficient x standardised value) with raw value and plain label; decision-tree path for the suggested field.
   - `messages.py`: code-to-text catalogue (English), one entry per reason code, warning and feature.
   - `compose.py`: `explain(...) -> Explanation` combining the above.
2. `Explanation` object (JSON-serialisable, separate from `ClassificationResult` and `MlFlags`):
   - `summary`: 1-3 lines for the health worker.
   - `classification_trace`, `flag_trace`, `review_trace`: audit detail with codes.
   - `limits`: standing notes (advisory, synthetic training, rule set version, model version).
3. `scripts/explain_demo.py`: prints both views for sample records (including boundary records).
4. `docs/modules/explain.md`, decision log entries, register update.

## Design
- Classification: the trace lists each criterion checked (oedema, MUAC, WFL/H z, infant criteria, danger signs, appetite), its value, its cut-off, and whether it fired. The deciding criterion is marked. Most severe criterion wins, as in Phase 2.
- Margins: show distance to the nearest cut-off (for example "MUAC 11.6 cm, 0.1 cm above the 11.5 cut-off"). Descriptive only.
- No "what to change" counterfactuals. Telling a worker which value would flip the class invites adjusting measurements.
- ML flag: top signals shown with direction and value ("MUAC is 125, probably recorded in mm"). Existing `top_signals` ranks by absolute size and drops the sign, so Phase 5 adds signed contributions.
- Review flag: already rule based with reason codes (D45). Phase 5 attaches the margin and cut-off that triggered each code.
- Two views from one object: `summary` (worker) and full traces (audit).

## Decisions needed
- Q1 Scope: explain the rules classification, the ML recording-error flag and the rules review flag in one `Explanation`. OK?
- Q2 Method: exact linear contributions and the tree path. No SHAP or LIME (extra dependencies, no gain for these models). OK?
- Q3 Counterfactuals: none. Margins to cut-offs only, as above. OK?
- Q4 Two views: short worker summary plus full audit trace. Worker summary max 3 lines. OK?
- Q5 Output: separate `Explanation` object, interfaces of `ClassificationResult` and `MlFlags` unchanged. OK?
- Q6 Language: English catalogue with stable codes now. Translation by the team later (D34). OK?
- Q7 HIV status: mention the HIV-positive MAM rule (D26) in the audit trace only, not in the worker summary, because the input is optional and sensitive (D7). OK, or show it to the worker too?

## Tests (planned)
- Faithfulness: logistic contributions plus bias equal the logit exactly; tree path ends at the model's own prediction.
- Every rule in the registry and every reason code, warning and feature has a message and a source.
- Deciding criterion in the trace matches `ClassificationResult` for all boundary records and a sweep of generated records.
- Explanation never changes `ClassificationResult` or `MlFlags` (equality before and after).
- Safety wording: no summary contains diagnosis phrasing; a SAM or urgent tier summary always states the referral action.
- Margins correct at exact cut-offs (MUAC 11.4, 11.5, 12.4, 12.5; z near -3 and -2).
- HIV wording absent from the worker summary (if Q7 accepted).
- Determinism and JSON round trip.
- Missing inputs and unable-to-classify cases produce a "what is missing" explanation.

## Exit criteria
Tests pass, `docs/modules/explain.md` written, decision log and register updated, limits stated plainly, open issues listed. Then WAIT before Phase 6.
