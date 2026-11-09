# Decision log

## Approved (Phase 0)
- D1. Age range 0-59 months.
- D2. MUAC is a primary criterion, for 6-59 months only. Not collected or classified for 0-5 months.
- D3. Oedema is entered by the user (grades +, ++, +++).
- D4. Tiers follow Malawi CMAM: low risk (counselling, routine monitoring); MAM (referral for further assessment); SAM or bilateral pitting oedema (urgent referral). Engine internally distinguishes SAM-OTP and SAM-inpatient, both mapped to the urgent tier. Final thresholds to be validated against current MoH guidance.
- D5. MUAC <12.5 cm is moderate.
- D6. Rule set pinned to Malawi CMAM 2016 (2nd Ed.) as `rules_v2016`, with a version field so a later edition can be added.
- D7. Optional HIV status input flag (sensitive data) for the HIV-positive MAM to OTP rule.
- D8. Low-risk tier retained (recommendation, not traced to a page).
- D9. Safety invariant: ML may add flags or escalate for review, never downgrade or override a rule. Enforced by tests in `tests/safety/`.

## Approved (Phase 1)
Phase 1 closed: approved by Edison 2026-11-07 (D10-D15 stand).
- D10. Linear interpolation of L, M, S between 0.5 cm WFL/H rows; tested against WHO published cut-offs.
- D11. Beyond +/-3 SD, WHO adjusted method for weight-based indicators (WFA, WFL/H) with flag `adjusted_beyond_3sd`. Length/height-for-age is never adjusted (confirmed by WHO's own +/-4 SD columns).
- D12. Flag `implausible_recheck_measurements` uses WHO limits (WFA <-6/>+5, LHFA +/-6, WFL/H +/-5). Flags never change the z-score. Phase 2 decides their effect.
- D13. Position handling follows WHO: standing height <=730 days gets +0.7 cm, recumbent >=731 days gets -0.7 cm, with a warning. This replaces my earlier "warn only" proposal because WHO documents the conversion. Easy to revert.
- D14. With oedema present, WFA and WFL/H are not computed (WHO rule); LHFA still is. Phase 2 uses the oedema grade directly.
- D15. Converted WHO CSV tables live inside the package (`src/thanzi_screen/anthro/reference_tables/`) with a SHA-256 manifest, so installs and Docker images work. `data/reference_tables/` is no longer used.

## Approved (Phase 2 spec answers, Edison 2026-11-07)
- D16 (Q1). Implausible-flagged z-scores are ignored. Valid MUAC and oedema are used. If no valid wasting assessment remains, output UNABLE_TO_CLASSIFY (recheck measurements). Never low risk.
- D17 (Q2). With oedema, WFL/H is excluded (D14); MUAC <11.5 is the wasting criterion for "oedema with severe wasting". Bilateral pitting oedema independently qualifies as SAM.
- D18 (Q3). SAM with essential information missing (appetite, danger signs, complications, clinical status): SAM_ASSESS, "Urgent assessment: determine OTP vs inpatient". Never defaults to OTP.
- D19 (Q4). Failed appetite test in SAM: inpatient. Confirmed by R3: anorexia (no appetite) is a danger sign, Table 5 p.16.
- D20 (Q5). Exactly 6 months uses the 6-59 month child pathway.
- D21 (Q6). MUAC under 6 months is ignored with a warning.
- D22 (Q7). Referral text is clearly marked placeholder until official wording is extracted. Destinations (NRU, OTP, SFP) come from R3.

## Approved (Phase 2 close, Edison 2026-11-07)
- D29 (I7). Implement the R3 Table 5 p.16 criterion "infant > 6 months and weighs < 3.0 kg" as an inpatient (NRU) trigger. Applied from 6.0 months (conservative at the boundary, consistent with D20) up to 59 months, independent of other inputs, ignoring implausible flags, with a "verify the measurement" warning. Rule ID `INF.WEIGHT_LT3KG`. `AnthropometryResult` gained an optional `weight_kg` field (backward compatible) to carry the weight.
- D30 (I10). Referral wording remains placeholder. Clinical referral rules are defined; only slip text is refined later.
- Phase 2 closed.

## Scope (Edison 2026-11-07)
- D31. Reuse of the Chakudya Nutrition Registry, its MCP server and Thanzi Coach, proposed in the team work plan (R11), was dropped because of added complexity. This repository stays independent. Team roles: Edison (engine, AI design), Hope Kalitera (architecture, backend and frontend, deployment, security), Maria Talimire (clinical validation). See `docs/challenge-alignment.md`.

- D32. WhatsApp channel dropped from the prototype because of the privacy policy (Edison 2026-11-07).
- D33. Synthetic data (Phase 3) carries a coarse district field, needed for the team's hotspot dashboard. Edison is not responsible for the dashboard.
- D34. Ownership (Edison 2026-11-07): local languages belong to the NLP/AI technical team with Edison's clinical input; point-of-care nutrition guidance belongs to Edison as Clinical Nutrition Lead (develop, validate, align with Malawi guidelines). Guidance content must come from approved Malawi sources, never invented. Not yet scheduled in a phase.

## Approved (Phase 3 spec answers, Edison 2026-11-07)
- D35. ML target for Phase 4 is A (detect measurement and data-entry errors) and B (flag borderline or inconsistent cases for clinician review) only. C (predict deterioration) is not implemented at this stage.
- D36. Single visit per child.
- D37. Prevalence and clinical-rate parameters are neutral placeholders marked ASSUMPTION; Edison will supply published Malawi figures later (reports only, no microdata).
- D38. MUAC-for-age z-score logic is not hard-coded until Edison uploads the official WHO tables (R8). MUAC is a configurable placeholder linked to WFL/H z.
- D39. 50,000 random records plus a small boundary set. CSV with SHA-256 manifest, standard library only.

- Phase 3 closed by Edison 2026-11-07; D40-D44 confirmed.

## Approved (Phase 4 spec answers, Edison 2026-11-07)
- D45. Target B is implemented as a **rules-based review flag**. An ML model for B exists only as a clearly labelled diagnostic replica, not production.
- D46. Models are plain-Python logistic regression and a shallow decision tree, standard library only at runtime. scikit-learn is optional and dev-only: try it on Termux first; if it will not install, skip it. (Edison's message was cut off after "If it fails then"; I read it this way.)
- D47. Target A is one flag for "possible recording error" plus a suggested field to recheck. No five-class classifier.
- D48. Operating point for A: at least 80% recall on errors Phase 1 flags miss, at most 10% of records flagged.
- D49. Output is a separate `MlFlags` object. `ClassificationResult` is unchanged.
- D50. Trained `models/*.json` are committed to git with their metrics.

## Approved (Phase 6 spec answers, Edison 2026-11-07)
- D74. Endpoints: `GET /health`, `GET /version`, `POST /v1/screen?view=worker|audit`. Single child per call, no batch.
- D75. Worker view: summary plus codes, no `referral_text`. Audit view adds the full `Explanation` and `referral_text`.
- D76. The Phase 2 HIV warning is neutralised in the worker view, original kept in the audit view. Condition from Edison: protect HIV privacy in worker responses.
- D77. Read-only alias `Explanation.worker_summary` added; `summary` stays.
- D78. Stateless, no body logging, unknown fields rejected. Condition from Edison: access restricted to Hope's gateway.
- D79. Degraded mode (rules only) if models are unavailable, with `explain_rules_only`.
- D80. Age input is `age_days` only.
- D81. FastAPI and pydantic at the HTTP edge only, framework-free `service.py`. Condition from Edison: run the full API tests in CI.
- D85. Phase 6 specification approved. No implementation until Edison says go.

## Interpretations of the Phase 6 conditions (need Edison's confirmation)
- D82. HIV privacy: no HIV information in any key or value of a worker response. Rule code `MAM.HIV_OTP` is shown as `MAM.OTP_ELIGIBLE` in the worker view (audit view keeps the real code), the HIV warning is replaced, request values are never echoed, and a fail-closed scan drops any field containing the text hiv. This is a display alias in the API only. Engine codes and the Phase 2 interface are unchanged.
- D83. Gateway restriction: `THANZI_GATEWAY_KEY` required (no start without it unless `THANZI_DEV_MODE=1`); header `X-Gateway-Key` on every route except a minimal `/health`; audit view needs a second key (`THANZI_AUDIT_KEY`), off if unset; docs and OpenAPI routes off outside dev mode; no CORS. Network isolation, TLS and rate limits are Hope's and are not enforced by code.
- D84. CI: GitHub Actions on push and pull request to `main`, Python 3.11 and 3.12, full test suite with `THANZI_REQUIRE_API_TESTS=1` (API tests cannot skip), OpenAPI drift check, Docker build and smoke job. Phase 6 does not close until CI is green on `main`.

## Phase 6 implementation decisions (Edison "go" 2026-11-07)
- D86. I20 decided by Edison: no programme in the worker view, neutral referral wording, real programme in the restricted audit view only. Applied to every MAM child (not just the HIV rule), because neutral wording on only the OTP case would itself reveal it. Worker view for MAM: `programme` is null, rule codes `MAM.HIV_OTP` and `MAM.SFP` both show as `MAM.REFER`, summary line 2 is the neutral action (`api/wording.py`), and every MAM response carries the same neutral warning, so its presence says nothing. Amends D75, D76 and D82 (which named `MAM.OTP_ELIGIBLE`). The worker response is identical for `hiv_positive` true, false and null (tested over about 1,700 records).
- D87. `oedema` is required: the engine has no "not assessed" for it, so a default of "none" would be a normal value filled in. Omitted `appetite` means `not_done`. Omitted or null danger signs, complications and the boolean findings mean not assessed (D25). `[]` means assessed, none present.
- D88. Keys must be at least 16 characters and the audit key must differ from the gateway key; otherwise the service does not start. Audit view without a valid audit key, or with audit off, returns the same generic 403.
- D89. `Explanation.flag_trace` may be None (rules-only explanation in degraded mode); `explain_rules_only` added. No existing function changed. Degraded `model_version` is `none`.
- D90. The gateway key is checked in middleware before routing and body validation, so unauthenticated callers cannot probe routes or validation. Only `/health` is open. Request bodies over 16 KB (declared length) are refused with 413 after authentication.
- D91. Runtime dependencies are pinned with compatible-release ranges in the `api` extra (`fastapi~=0.162.2`, `pydantic~=2.14.3`, `uvicorn~=0.54.0`; dev `httpx~=0.28.1`) so the committed OpenAPI file stays reproducible in CI. Engine dependencies stay empty.

## Phase 6 close (Edison 2026-11-07)
- D92. Phase 6 closed on Edison's instruction to start Phase 7. CI run #2 on `b817e9c` is green (Edison's screenshot). CI #1 failed on a YAML syntax error in `ci.yml` (unquoted `: ` in a `run:` value), fixed in `b817e9c` with a YAML parse test. The assistant did not see the individual Docker steps; Edison to confirm they ran (I22).

## Phase 7 decisions (Edison approved Q1-Q8 on 2026-11-07; implementation follows the approved spec)
- D93. Phase 7 approved as specified (`docs/specs/phase-7-spec.md`). Answers: Q1 yes (CI hardening); Q2 yes, subject to licence and security checks (done, see register R13); Q3 report coverage only, threshold after review; Q4 yes (constraints file); Q5 report measured load only, no targets until Hope and UniPod give server specifications; Q6 GitHub release with image tarball and SBOM, GHCR publishing left to Hope; Q7 I5 stays open until sample WHO Anthro output is supplied and compared; Q8 tag `0.7.0` as Release Candidate, Not Validated. No change to Phases 1-6 behaviour.
- D94. Rule traceability is by observation: a pytest plugin (`tests/_trace_plugin.py`) records which test makes which rule appear in `rules_fired`. A rule with no test fails `scripts/build_traceability.py --check` (CI and release). Result on `0.7.0`: all 23 rules exercised. This shows a rule was run, not that its threshold is clinically right.
- D95. The case pack (`docs/testing/case-pack.xlsx`, 65 synthetic scenarios) is generated from the engine under `rules_v2016`, rules only (no ML). The two reviewer columns are blank for Maria; `--check` ignores them so a filled copy still passes. It is not a validation.
- D96. `scripts/smoke_api.py` is the black-box check used by CI against the container and by Hope after deployment. CI now generates throwaway keys per run (`openssl rand -hex 24`) and checks that the container log holds no keys or request values.
- D97. `scripts/load_probe.py` reports measured latency and throughput only. No pass or fail threshold exists (Q5). Numbers in the test report come from a 1 vCPU build environment, not UniPod.
- D98. `constraints.txt` pins every direct and transitive package (generated on Python 3.12, installed and tested on 3.11 and 3.12). CI, the Dockerfile and the release build install with `-c constraints.txt`. Refresh with `scripts/refresh_constraints.py`; Dependabot does not read it.
- D99. Secret scan: gitleaks 8.30.1 binary (SHA-256 checked in CI). The first scan of history found one match: the throwaway test keys printed in the Phase 6 `ci.yml` (commit 7b59256). They protected a container that lived for one CI run. `.gitleaks.toml` allowlists exactly those two values and nothing else; a test enforces that.
- D100. CI hardening: Actions pinned to commit SHAs (checkout v4.3.1, setup-python v5.6.0, upload-artifact v4.6.2, trivy-action v0.36.0), job timeouts, concurrency cancel, pip cache, `pip-audit` on the pinned set (no known vulnerabilities on 2026-11-07), Trivy image scan failing on fixed HIGH and CRITICAL findings, CycloneDX runtime SBOM, Dependabot for Actions, Docker and pip. The base image `python:3.12-slim` is not pinned by digest: the build environment cannot reach a registry. Dependabot watches the tag; Hope may pin a digest (runbook).
- D101. Robustness tests (malformed, oversized, odd-typed, hostile values, wrong methods and content types) found one defect, recorded as I28 and not fixed here. It is marked as a strict expected failure so the suite fails when someone fixes it and prompts removal of the marker. Property tests (monotonic severity, missing information never lowers urgency, danger signs and complications never lead to outpatient care, output invariants) found no defects.
- D102. Release: tag `v0.7.0` triggers `release.yml`, which verifies, builds, scans and smoke tests the image, then creates a GitHub pre-release titled "Release Candidate, Not Validated" with the image tarball, SBOMs, checksums and test evidence. No registry push. `deploy/docker-compose.example.yml` is an example only.
- D104. First GitHub run (Dependabot pull requests #1-#3, Edison's logs, 2026-11-08): `test` (3.11 and 3.12), `dependencies` and `secrets` jobs passed on GitHub: 590 passed and 2 expected failures, coverage 98%, all 23 rules traced, OpenAPI and case pack current, `pip-audit` clean, gitleaks clean with the allowlist. The `docker` job built the image, then Trivy failed it on two HIGH findings with fixes available in the Debian 13 base image's `zlib1g` (CVE-2026-76844, CVE-2026-85091; fixed version 1:1.3.dfsg+really1.3.1-1+deb13u1). The gate worked as designed. Fix: `apt-get upgrade` in the Dockerfile before our dependencies. Not run here (no Docker); the next CI run shows whether it clears the scan. Container smoke steps still have not run.
- D108. Deployment runbook gains two sections, "Tools and dependencies" and "Target hardware", for the programme technical lead (Edison, 2026-11-08). The stated hardware is development workstations (Intel Core 9, NVIDIA RTX A4000 16 GB, or the UniPod-confirmed GPU configuration); the engine is CPU only and does not use the GPU. No code or behaviour change.
- D107. Release workflow ran on tag `v0.7.0` on 2026-11-08 and passed (Release #1, 2m 38s), on the same commit as CI #10 (green). Edison reported both from the GitHub run list; the assistant did not see the logs. The pre-release "Thanzi screening engine v0.7.0: Release Candidate, Not Validated" is published. Edison's screenshot of the assets shows: `thanzi-screen-v0.7.0-image.tar.gz` (47 MB), `thanzi-screen-v0.7.0-sbom-runtime.cdx.json`, `thanzi-screen-v0.7.0-sbom-image.cdx.json`, `SHA256SUMS`, `openapi.json`, `case-pack.xlsx`, `test-report.md`, `traceability.md`, `deployment-runbook.md`. Not yet done by anyone: checking the checksums against the downloaded tarball, loading the tarball into Docker, running the compose example on a Docker host. The release is still not validated (clinical review, UniPod hardware, real data).
- D106. Edison's decisions on the Phase 7 open items, 2026-11-08. I28: fix the underlying defect and add regression tests (done, below). I29: no file-based keys; keep environment-based secrets. I31: Edison will review the MAM referral wording and the clinical case pack himself as a dietitian. I5: wait for sample WHO Anthro output before comparing. UniPod server specifications: wait for the UniPod technical lead. Network isolation: Edison hopes to coordinate with UniPod before deployment (I21 stays open). I28 fix: `compute_anthropometry` now rejects a length or height that is not positive after the 0.7 cm age-convention conversion and rounding, raising `InputError` (the API returns 422, no value echoed). Cause: the conversion for a length measured on a child over 730 days subtracts 0.7 cm, and rounding turned values near zero into 0, so the z-score step raised a bare `ValueError`. Valid measurements and all plausible-but-extreme values (flagged as implausible, as before) behave exactly as before. No change to rules, thresholds, wording or the OpenAPI document. The two strict expected-failure markers are replaced by regression tests.
- D105. Phase 7 closed by Edison 2026-11-08: CI on `main` is green, including the `docker` job (Trivy scan and container smoke steps) after the zlib fix (D104). The assistant did not see that run's logs; this rests on Edison's report. The release workflow has not run yet; the `v0.7.0` tag is its first run. Next: tag `v0.7.0` after the closing commit is green. No Phase 8 until Edison says so.
- D103. Coverage is reported, not gated (Q3). First measurement on `0.7.0`: 98% line and branch overall on both Python versions; lowest file `data/validate.py` at 80%. Edison sets any threshold after review.

## Approved (Phase 5 spec answers, Edison 2026-11-07)
- D58. Scope: one `Explanation` covers the rules classification, the ML recording-error flag and the rules review flag.
- D59. Method: exact linear contributions for the logistic model and the tree path. No SHAP or LIME.
- D60. No counterfactuals ("what to change"). Margins to cut-offs only.
- D61. Two views from one object: worker summary (max 3 lines) and full audit trace.
- D62. Output is a separate `Explanation` object. `ClassificationResult` and `MlFlags` are unchanged.
- D63. English message catalogue with stable codes now; translation by the team later (D34).
- D64. HIV wording appears in the audit trace only, never in the worker summary (D7).

## Implementation interpretations in Phase 5 (confirmed by Edison 2026-11-07)
- D65. Worker summary lines: (1) class phrase plus up to 3 deciding reasons, or what is missing; (2) the action, taken from `referral_text` with the placeholder prefix removed (D30); (3) the ML recording check and the review reason, combined. Line 3 is omitted when neither applies.
- D66. For rule MAM.HIV_OTP the worker action line says "Refer for admission to OTP" with no HIV wording (D64). `ClassificationResult.referral_text` itself still contains HIV wording (Phase 2 is unchanged), so the Phase 6 API must not show raw `referral_text` in the worker view for that case (I17).
- D67. Infant rule INF.WFA_CLINICIAN yields class MAM (I9). The worker line says weight-for-age is very low and a clinician should assess, not "moderate acute malnutrition".
- D68. Worker view shows the 2 largest signals that raise the error probability. The audit trace lists all 36 signed contributions. The Phase 4 `top_signals` method (magnitude, no sign) is left unchanged.
- D69. Margin = value minus cut-off. A value exactly on a cut-off is reported as such and counts as the less severe side, matching the rules (MUAC at 11.5 is not severe, z of -2.00 is not moderate, A1).
- D70. Wording is a draft. Phase 5 messages need review by clinicians and health workers before any use.
- D71. I17 decided (Option 1): Phase 2 stays unchanged. The Phase 6 worker-facing API uses the `Explanation` worker summary (exposed as `worker_summary`) and never raw `ClassificationResult.referral_text`.
- D72. I18 approved: Phase 5 wording stays a draft until a qualified clinician (Maria Talimire or another) has reviewed it and health-worker testing is done. Both pending.
- D73. Phase 5 closed by Edison 2026-11-07. Phase 6 spec drafted; approved the same day (D74-D85).

## Implementation interpretations in Phase 4 (confirmed by Edison 2026-11-07)
- D51. Features use only recorded values, Phase 1 z-scores and flags, and Phase 2 outputs (36 features, listed in `ml/features.py`). They include "would a digit swap or a 10x weight shift make this plausible" checks and the distance of the age to an exact 6-month multiple.
- D52. "Errors Phase 1 misses" means injected-error records with no Phase 1 implausible flag.
- D53. `MlFlags` carries the ML error flag and the rules-based review result side by side, each labelled by source.
- D54. Age heaping is detected almost perfectly only because the synthetic injection rounds ages exactly. Real heaping is fuzzy, so this will not transfer. The same feature flags a child legitimately aged exactly 12 months (the boundary stress test shows this).
- D55. Results on synthetic data are high (AUC about 0.997). That reflects clean synthetic errors, not real-world performance.
- D56. Threshold chosen on validation by maximising recall on Phase-1-missed errors under the 10% alert cap.

- D57. Phase 4 closed by Edison 2026-11-07 (D45-D56 confirmed). Phase 5 spec approved the same day (D58-D64).

## Implementation interpretations in Phase 3 (confirmed by Edison 2026-11-07)
- D40. Target B labels (`review_reasons`) are built deterministically from engine outputs: unable to classify, missing assessment, implausible value, weight under 3 kg verify, MUAC vs WFL/H discordance, near MUAC threshold (within 0.2 cm), near WFL/H threshold (within 0.1 z). Margins are assumptions. A model can only learn this function, not clinical truth.
- D41. Four injected error types: weight decimal shift, length digit transposition, MUAC unit error (cm recorded as mm), age heaping to 6-month multiples. Overall rate 4% (assumption). `injected_error` records the true label.
- D42. Boundary set has 16 records: MUAC 11.4/11.5/12.4/12.5, WFL/H near -3.01/-3.00/-2.01/-2.00 (weights are rounded to 0.01 kg, so z lands within about 0.01 of target), ages 182 and 183 days, weights 2.99/3.00/3.01 kg at 8 months, oedema +/++/+++. They carry split `boundary` and are excluded from training.
- D43. The 28-district list in `config.py` is from my own knowledge and must be checked against the official list. Districts are assigned uniformly with no spatial pattern.
- D44. Generated CSV (about 11 MB) is git-ignored. It is regenerated from seed and config. The SHA-256 can differ between Python versions or platforms because of floating-point math; the manifest records the Python version.

## Implementation interpretations in Phase 2 (D23-D28 and A1, A2 confirmed by Edison 2026-11-07)
- D23. Stricter reading of D16: if WFL/H is flagged implausible and MUAC is normal, return UNABLE_TO_CLASSIFY rather than low risk (a suspect weight or height could hide wasting). A valid abnormal MUAC or oedema still classifies.
- D24. Added input `clinically_well_and_alert` (R3 OTP criterion). Lethargy or unconsciousness as danger signs force "not well and alert".
- D25. Danger signs or complications are `None` when not assessed, empty set when assessed and absent.
- D26. HIV-positive MAM meeting OTP conditions: classification MAM, tier MAM, programme OTP. The spec draft said urgent tier; R3 does not make this child SAM, so I did not.
- D27. Infants: exactly 45 cm applies the WFL criterion (conservative); visible severe wasting is accepted at any length when entered true.
- D28. User-facing tier "recheck" added as a fourth tier for UNABLE_TO_CLASSIFY.

## Open issues
- I1. Licences for WHO tables and the CMAM PDF unconfirmed; raw files kept out of git.
- I2. Inputs needed for the OTP vs inpatient split: appetite test, danger signs, medical complications.
- I3. (closed) Phase 1 decisions resolved: D10-D11.
- I5. Cross-check against WHO Anthro software output on sample records (still open). Chapter 7 now verified from the WHO book (R6): adjusted method and worked examples confirmed. Oedema rule and plausibility limits are not in the book chapter and rest on WHO anthro documentation (R6b). Q7 (2026-11-07): stays open until Edison supplies sample WHO Anthro output and it is compared.
- I6. Phase 2 must define how implausible-flagged values affect classification.
- I4. Confirm with MoH Nutrition Unit that no edition newer than 2016 applies.
- I2. (closed in Phase 2) Danger signs, complications and appetite role extracted from R3 pp.11, 16.
- I6. (closed) Resolved by D16, D23.
- I7. (closed) Implemented as D29.
- I8. (closed) D26 confirmed 2026-11-07.
- I9. (closed) A2 confirmed 2026-11-07.
- I10. Official referral slip wording: placeholders remain by decision (D30); refine later.
- I11. (closed) A1 and D23 confirmed 2026-11-07.
- I12. R8 (WHO arm-circumference-for-age tables) pending upload from Edison. Until then MUAC stays a placeholder (D38).
- I13. R9 (published Malawi prevalence figures) pending from Edison (D37).
- I14. Real recording errors are messier than the four injected types. Revalidate on real data before any use.
- I15. Fairness across districts, age bands and sex cannot be tested on synthetic data (districts carry no signal). Needs real data (work plan Week 6).
- I16. Age flag treats exact 6-month-multiple ages as suspicious. Decide how to handle ages that come from a recorded date of birth.
- I17. (closed) Decided by D71: the Phase 6 worker view never uses raw `referral_text`.
- I18. Phase 5 wording (`explain/messages.py`) needs review by Maria Talimire or another qualified clinician, and health-worker testing (D72). Pending.
- I19. Chichewa translation of the message catalogue pending; owner per D34.
- I20. (closed) Decided by Edison 2026-11-07: no programme in the worker view, neutral wording, details in the audit view. Implemented as D86. Residual: a worker who is told the real programme by a clinician can still infer it; that is outside the API.
- I21. Network isolation of the API (private network, no public port, only Hope's gateway) is deployment work for Hope. Needs her confirmation before any deployment.
- I22. (closed D92, CI #2 green; Docker step list to be confirmed) First CI run unverified until Edison pushes. GitHub Actions pinned to major versions, not commit SHAs. Phase 6 closes only when CI is green on `main`; the Docker job and Python 3.11 were not run in the build environment (no Docker, Python 3.12 only).
- I23. The neutral MAM wording (`api/wording.py`) is a draft. Maria Talimire or another clinician must confirm a worker can act on it, and workers must be able to learn the programme through the clinic's own process (D72).
- I24. The audit view carries HIV information and the real programme. Who may hold the audit key, and how access is logged, is Hope's decision (D83).
- I25. D82-D84 interpretations were not explicitly confirmed by Edison in the go message. Treated as accepted unless he says otherwise.
- I26. Load measured only in a 1 vCPU build environment (D97); not tested on UniPod servers. `starlette.testclient` prints a deprecation notice about `httpx` (test client only, not the runtime); revisit when the pinned versions move.
- I27. (closed D93) Phase 7 spec approved; CI gaps found in review are addressed in D96-D100.
- I28. (closed D106, fixed before the `v0.7.0` tag) WAS:  `length_height_cm` extremely close to zero (1e-10 and below) reaches the length-for-age step and raises `ValueError`, which the API returns as a generic 500 instead of a 422. Stateless, no data leaked, but wrong. Fixed by rejecting a non-positive length after conversion as `InputError`; regression tests added. Implausibly small but positive lengths are still computed and flagged as implausible, as before.
- I29. (closed D106) Decided by Edison 2026-11-08: no file-based keys; environment-based secrets stay. Context: the image reads keys from environment variables only; no `*_FILE` support. Keys are readable with `docker inspect` on the host. Revisit only if Hope or UniPod require it.
- I30. (closed D107) The container smoke steps passed on `main` and the release workflow passed on the `v0.7.0` tag, per Edison. Remaining unchecked: the published tarball loaded and run on a Docker host, and checksums verified against a download.
- I31. The worker wording shows z-scores to two decimals, so a child at -2.004 is classified moderate while the text reads "-2.00 is from -3 up to -2". Correct but looks contradictory at an exact boundary. For clinical review with I18 and I23. Edison (2026-11-08, D106) will do the review of the MAM wording and case pack as a dietitian; Maria is no longer the only reviewer.

## Preterm integration (branch feat/preterm-integration, 2026-11-08). Proposed, for Edison and clinician review
- D109. The preterm engine is added as `thanzi_screen.preterm` with `engine.py`, `preterm_rules.json` and `fenton2025_lms.json` byte-for-byte as supplied. Integration settings live in a separate `routing_config.json`.
- D110. Routing is automatic inside `POST /v1/screen` (one door, so a preterm baby cannot be sent down the wrong path by choosing an endpoint). Birth fields are optional; without them behaviour is unchanged.
- D111. Level map: routine -> low_risk, follow_up -> mam, refer -> mam, urgent_refer -> urgent. No new level. See I32.
- D112. Existing danger-sign, complication, too_weak_to_suckle and failure_to_gain_weight inputs feed the preterm triggers. Signs the CMAM list lacks go in a new `neonatal_danger_signs` list, not in the CMAM `DangerSign` enum (which would change CMAM rules).
- D113. `ml/features.FEATURES` is frozen (`load_models` rejects a different list). Preterm columns are a separate `PRETERM_FEATURES`; `rule_level` is excluded and refused as a label.
- D114. Unit guards: `birth_weight_g` 200 to 8000, `weight_kg` 0.2 to 10 on the preterm route. A kg/g swap is rejected, not converted.
- D116 (Edison, 2026-11-08). follow_up keeps its own disposition: no under-5 tier (null), not forced into mam or low_risk. Supersedes D111 for follow_up.
- D117. Corrected-age end for GA 32 to under 37 weeks is PROVISIONAL (24 months placeholder) and flagged in responses until verified against the clinical reference.
- D118. Term babies under 2500 g use chronological age; correction only for babies born preterm.
- D119. Danger signs and complications require referral. Hypoglycaemia (complication alone = refer; urgent only if stated not correcting) and oedema (per grade, all refer for now) follow the approved protocol via `routing_config.json`.
- D120. Length and position are optional only on the preterm route; oedema stays explicit.
- D121. Unknown gestational age with birth weight under 2500 g: under-5 flow, warning, `clinical_assessment.needed`; GA is never assumed.
- D122. Display-only wording: worker view says "faltering growth (not gaining weight)"; codes, rule ids and the audit trace keep CMAM terms.
- D123. Urgent triggers are driven from `preterm_rules.json` (`urgent_triggers.rules`); `engine.py` reads them; tests check agreement. The "not gaining" age now uses `min_age_days`.
- D124 (Edison, 2026-11-08). 24-month corrected-age end approved; no longer provisional. Supersedes D117.
- D125. Hypoglycaemia and oedema implemented per CMAM 2016 Table 5 (the guideline encoded in rules_v2016.py): the hypoglycaemia complication, and any oedema grade in an infant, give urgent_refer. Supersedes D119. Oedema is a clinical sign, not growth, so the growth rule is unchanged.
- D126. Null tier allowed for follow_up if the gateway supports it; `preterm_level` remains the separate disposition. Gateway support is still to be confirmed.
- D127. Corrected age feeds all age-dependent CMAM criteria (MUAC from 6 months, infant criteria) automatically; thresholds unchanged (test: result equals the plain under-5 result at the corrected age). Closes I41.
- D115. The ML recording-error flag is not run on the corrected-age route (models trained on chronological ages).

## Open issues from the preterm integration
- I32 (decided, D116; gateways must accept a null tier). follow_up has no under-5 tier. Default follow_up -> mam over-refers late-preterm LBW babies who only need weekly review; follow_up -> low_risk would hide facility-KMC and unsupervised-home-care babies. Clinician to choose; one line in `routing_config.json`.
- I33 (approved, D124). The brief gives the corrected-age end (age 3) only for GA under 32 weeks. 24 months for 32 to under 37 weeks is a placeholder.
- I34 (decided, D118). Term babies under 2500 g (GA 37 or more) are routed to preterm under 50 weeks PMA but get chronological age afterwards, not the brief's literal formula (at most 3 weeks of correction). Confirm.
- I35 (hypoglycaemia changed per D119; rest still to confirm). Mapping under-5 inputs to preterm triggers: hypoglycaemia (any) -> "not correcting"; severe_dehydration -> dehydrated; any danger sign or complication -> sick (refer); failure_to_gain_weight true -> 0 gaining days; unconsciousness counts as lethargic.
- I36 (decided, D120). Preterm and corrected-age routes require the under-5 fields `length_height_cm`, `measure_position` and `oedema`, though the preterm engine treats length as optional. Make them conditional?
- I37 (decided, D121). Born under 2500 g with gestational age unknown: under-5 flow with a warning, no preterm screen. GA is often unknown in clinics; confirm, or define a fallback.
- I38 (approved, D125). Oedema on the preterm route raises the level to refer (never urgent). The preterm engine does not read oedema.
- I39 (decided, D122). The under-5 engine uses "failure to gain weight" (CMAM Table 5 text and the `failure_to_gain_weight` field), which conflicts with the "faltering, never failure" rule on the corrected-age route. Not changed. Display-only rename?
- I40 (decided, D123). In `engine.py`, the urgent-trigger set and the "not gaining" age (`> 14`) are hardcoded; the file's `min_age_days` is used only by the growth block. Tags in `preterm_rules.json` document but do not drive them. Logic left as supplied.
- I41 (decided, D127). Corrected age applies CMAM thresholds (MUAC from 6 months, the infant criteria) to corrected age. Confirm.
- I42 (open: CI first build). No Docker build was run in this environment (CI does it). Data shipping was checked with a clean non-editable install.

## Local LLM client (branch feat/llm-client, 2026-11-08). Proposed, for Edison's review. Not a numbered phase
- D128. New package `thanzi_screen.llm`, independent of screening in both directions: it imports nothing from the engine, and no engine module imports it (only `api/app.py` and `api/llm_routes.py` mount it). Enforced by AST tests that were checked to fail when either rule is broken. Model text is never an input to a rule, flag, explanation or referral.
- D129. Provider-agnostic: `LLMProvider` contract with Ollama, llama.cpp, OpenAI-compatible and mock providers and a registry. Changing model, server or provider is a setting; a new server is one class and one `register_provider` call. Callers depend on the small `TextGenerator` protocol.
- D130. HTTP transport is httpx, in a new optional extra `llm` (`httpx~=0.28.1`, already pinned in `constraints.txt`, so no new packages). `dependencies` stays empty and the release image and its install line are unchanged (a test asserts it). `deploy/Dockerfile.llm` adds httpx on top of the release image. The package imports without httpx.
- D131. Privacy and security defaults: feature off; endpoint must be local or private unless `THANZI_LLM_ALLOW_REMOTE=1` (then https only); no credentials in URLs, no redirects, proxy variables ignored; reply size cap; prompts, replies, URLs and server error text never logged or placed in exceptions; tests use synthetic text and loopback fake servers only.
- D132. Low-resource defaults: one inference at a time with a 5 s bounded wait, 60 s deadline, one retry for connection errors and 429/502/503/504 only (never timeouts or 500, which is usually out of memory), context 2048, 256 output tokens, keep-alive 5 minutes, default model `qwen2.5:1.5b`.
- D133. API integration: optional `GET /v1/llm/health` and `POST /v1/llm/generate` behind the gateway key. Absent unless `THANZI_LLM_ENABLED=1`, so `openapi.json` is unchanged. An enabled but invalid configuration stops start-up. `/health` does not look at the model. `create_app` gains an optional `llm` argument and a lifespan that closes the client.
- D134. Qwen3-style visible reasoning: Ollama `think` setting plus provider-independent removal of `<think>` text (closed, unopened and unclosed forms).

## Open issues from the local LLM client
- I43 (decided 2026-11-08 by Edison: keep the route as it is; off by default). WAS: does Edison want `POST /v1/llm/generate` at all? The Python client may be enough for now. The route takes free text; the client cannot tell identifiable from synthetic text, so keeping patient records out is a rule for callers. Default off either way.
- I44. Model choice and licences are not verified. Qwen2.5 sizes do not all share one licence (as far as I know, the 3B differs). Read the model card, then fill in the register (R16, R17) before any deployment. No weights in the repository.
- I45. Not tested against a real Ollama or llama.cpp server, a real Qwen model, Docker or UniPod hardware. Only fake loopback servers and `MockTransport` were used. The compose example is untested. Needs one real run and a memory and latency measurement on the target machine. Python 3.11 not run locally (CI runs it).
- I46. Delivery: the release image carries the code, switched off, without httpx. Hope decides whether to use the derived image, and where the model server runs (a private network with no route out; models must be put on a volume beforehand).
- I47. Not done: streaming, circuit breaker, output safety filtering. Model text is unreviewed and must not reach health workers without clinician review (same rule as the Phase 5 wording, I18).

## NLP for free-text notes (`thanzi_screen.ml.nlp`, 2026-11-08). Add-on, not a numbered phase. For Edison's review
- D135. New package `thanzi_screen.ml.nlp` under the machine learning modules: extraction of findings from a free-text note, a cross-check against the structured entry, and best-effort identifier masking. Standard library only; `dependencies` stays empty.
- D136. The lexicon is data (`lexicon.json`, shipped as package data), validated on load. Every concept maps to a finding already encoded in `thanzi_screen.rules` (CMAM 2016 Table 5); a test checks each value exists in the engine enums. Nothing here adds a clinical criterion.
- D137. Method: lexicon match plus negation and uncertainty scope. Transparent and deterministic. Not a trained model.
- D138. A negation or uncertainty trigger reaches at most 5 tokens before or 3 after a term, and never across a comma, full stop, semicolon, colon, line break or contrast word ("but", "however", "although", "though", "except"). Chosen so that an error shows as a missed negation (an extra check), not a hidden finding. The window sizes are ASSUMPTIONS.
- D139. One typing error is tolerated only in single words of 8 or more letters with the same first letter. Short words never match fuzzily.
- D140. Results never contain the note's own words: a mention carries the concept, the polarity and the matching lexicon term. Tested with made-up names.
- D141. The cross-check is advisory (D9). It reports a finding in the note that the entry lacks (or lacks "not assessed"), a possible one, a note that denies something the entry records, and appetite disagreement. It never edits a field. Messages are worker-facing wording and are DRAFT (I49).
- D142. Independence in both directions, enforced by AST tests that were checked to fail: `ml/nlp` imports nothing from `thanzi_screen`; nothing outside it imports it. It takes plain values, not engine objects.
- D143. `redact` masks phone numbers (Malawi formats), email addresses, dates, runs of 8 or more digits, and names after a label. Best-effort. It does not remove the rule that identifiable text stays out of places it should not go (I43).
- D144. Not wired into `POST /v1/screen`, the flags or the explanation layer. No route, schema or `openapi.json` change. No trained text model, because there is no real authorised note data (I48). HIV is excluded from the lexicon and the loader refuses it (D7, D86).

## Open issues from the NLP add-on
- I48. No real or authorised clinical notes exist, so nothing here is validated. The 30 gold notes are a regression set written by the team. Before any use, collect de-identified notes with approval, label them with Maria, and measure recall and false alerts. A trained model comes only after that.
- I49. The lexicon is a draft: English only, no Chichewa terms, not reviewed by a clinician. Maria to review the terms and the worker-facing messages. Chichewa terms to be supplied by someone who can validate them. Same status as the Phase 5 wording (I18).
- I50. Does Edison want it wired in (a field on the screen response, or a separate route)? That needs a schema and an `openapi.json` change and a privacy decision: the note text would travel through the gateway.
- I51. Known limits: negation ends at a comma; no time, family-history or who-is-described handling; "fever" is not mapped to the high-fever danger sign.
- I52. `redact` cannot find a name written without a label, a village or a nickname. Phone and ID patterns are Malawi-shaped and may miss other formats.

## Deep learning (`thanzi_screen.ml.dl`, 2026-11-08). Add-on, not a numbered phase. For Edison's review
- D145. New package `thanzi_screen.ml.dl` under the machine learning modules: a small neural network, hardware-aware preset choice, training and inference, beside the Phase 4 models and the NLP add-on. Standard library only; `dependencies` stays empty and no extra is added. No numpy, PyTorch, ONNX or scikit-learn at runtime. Reason: the engine is standard library by design (Docker-ready, minimal dependencies), and a PyTorch install is often impossible on the Android and Termux setup the work is done on.
- D146. Lightweight by construction: presets `tiny` (16), `small` (32-16), `base` (64-32); a parameter budget of 20,000 enforced when a network is built or loaded; ReLU and Adam only. The budget is a deliberate stop, raised only with `max_params=`.
- D147. Hardware awareness: CPU count, available memory (None if hidden) and a short timing loop pick the largest preset that should train within a time budget (`--preset auto`). The estimate is rough. Hardware facts are never written into model files or cards, so training stays reproducible.
- D148 (superseded by D153). Advisory and not wired in. Same rule as D9. Nothing in `api`, `service` or the screening path imports `ml.dl` (AST test, checked to fail). Both model files carry `production: false`. No route, schema or `openapi.json` change. Wiring it in is Edison's decision (I56).
- D149. Same data, features, splits, operating-point rule and report as Phase 4 (`FEATURES`, the leakage guard, `choose_threshold`, `full_report`), so results compare directly. The card compares with the logistic model only when both were trained on the same dataset (manifest hash).
- D150. Deterministic: same dataset, seed and settings give identical JSON (a test compares bytes). Hidden layers use ReLU, so only the sigmoid and softmax outputs touch the maths library.
- D151. Explainability is minimal: `top_signals` removes one input at a time (sets it to the training mean) and ranks by the change in output. It is not connected to the Phase 5 explanation layer.
- D152. No deep text model. The NLP add-on stays lexicon-based because no real, authorised note data exists (D144, I48). The network code is generic and could take a text encoder later, after that data exists and the licence and privacy checks are done.

- D153 (Edison, 2026-11-08: "switch on to production"). The deep flag runs in `POST /v1/screen` as `ml_flags.deep_recording_error`, beside the logistic flag, which stays and still feeds the Phase 5 explanation. Both deep model files carry `production: true`. "Production" here means it runs in the API as an advisory flag with the same status as the logistic flag: synthetic data only, not validated on real children. It does not replace the logistic flag and does not change a classification, tier, reason, review or wording. Supersedes D148.
- D154. Failure isolation. The deep flag is computed from the feature dict the screen already built, inside a guard: any failure is logged by exception type only (never the message or the input) and the response is exactly what it would be without the flag. Tests break the model on purpose to prove it.
- D155. Off switch and degradation. `THANZI_DEEP_ENABLED=0` (also false, no, off) turns it off at start-up with no rebuild. Missing or mismatched deep files leave the flag absent and `/health` at `ok` (that status still means the logistic models). It is not run in degraded mode, and not on the corrected-age route (same as D115).
- D156. Contract change, additive only. `MlFlagsOut.deep_recording_error` (optional) and `VersionResponse.deep_model_version` (null when not loaded). `docs/api/openapi.json` regenerated, CI `--check` passes. Worker view carries no probability. Existing fields are unchanged.

## Open issues from the deep learning add-on
- I53. Results are on synthetic data with injected errors. The task is close to linearly separable, so the network matches the logistic model and no more. No claim about real data. Needs real, authorised records, as for Phase 4 (I14).
- I54. Auditability. A network is harder to explain and to check for fairness than the logistic model (I15). `top_signals` is an occlusion check only. Before any use, decide whether Phase 5 explanation wording should cover it.
- I55. Speed and size. Pure Python took about 3.5 minutes (small preset, one core) here and will be slower on a phone. A numpy or PyTorch path would help for larger models but adds packages, so it needs a separate reviewed change. Not measured on Termux or UniPod hardware.
- I56 (decided 2026-11-08 by Edison: switch on to production; D153 runs it beside the logistic flag, not instead of it). WAS: does Edison want it wired in (a field on the screen response, or replacing the logistic flag)? That needs a schema and `openapi.json` change, a decision on which model is `production`, and clinical review of the wording. `compare_record` exists so the two can be run side by side first.
- I57. Gateway and clients. The new response field is additive, but a client with a strict schema would reject it. Hope to confirm the gateway and any front end accept `deep_recording_error` and `deep_model_version`, or switch the flag off with `THANZI_DEEP_ENABLED=0` until they do.
- I58. Two flags can disagree (one flags, one does not). The API returns both and decides nothing. Maria and Edison to decide what a health worker should see in that case, and review the wording (same status as I18).

## Growth monitoring (`thanzi_screen.growth`, 2026-11-08). Add-on, not a numbered phase. For Edison and Maria to review
- D157 (Edison, 2026-11-08: add growth monitoring so the system can detect growth faltering). New package `thanzi_screen.growth`: weight-gain velocity (g per day) between an earlier visit and this one, compared with the ASPEN reference range (R19). Standard library only; it reads the existing WHO weight-for-age table only to check that a weight is plausible. Rule-based, not machine learning, so it works in degraded mode.
- D158. Stateless by design. The engine stores nothing and takes no child identifier (D25, Phase 6), so it cannot look up an earlier visit. The caller sends one optional `previous_measurement` (`age_days`, `weight_kg`, nothing else, no identifiers). The gateway or app, which already holds the child's history, supplies it. Response: optional `growth_monitoring`. Additive contract change; `openapi.json` regenerated.
- D159. Advisory only (D9). The result never changes a classification, tier, reason, review, ML flag or wording. Tested on both views over many records. A child can be `low_risk` and still carry a growth flag. Only the under-5 route runs it. Preterm and corrected-age babies get a warning that it was not run, because the reference is for term infants and band choice would need corrected age.
- D160. Only the weight velocity rows are used. Length and height velocity are not: from 12 months the source gives a single value, not a range, and length measurement error is large next to a daily rate of 0.3 to 0.5 mm. Rows for 7 years and over are not transcribed (the engine is under 5). The preterm monitoring rows (15 to 20 g/kg/d, length over 1 cm/week, head circumference 0.8 to 1 cm/week, initial loss up to 15% regained in 10 to 14 days) are not used: they need per-kg rates and head circumference, and belong with the preterm engine.
- D161. Comparison rule. Average daily gain = weight change in grams / days. The range is averaged over the days the interval spends in each age band (an interval that crosses a band edge is compared with a blend). Below the low end is `below_range` and flagged. A gain on a range end counts as inside. Above the range is reported, never flagged (it can be catch-up growth or oedema). Weight loss is `below_range` with its own message. Wording is hedged: "may be a sign of growth faltering". Rates are rounded to 6 places before comparing so floating-point error cannot push a value that is exactly on a range end outside it.
- D162. Not assessed, with a reason, instead of a guess: `interval_too_short` (under 28 days), `implausible_weight` (either weight outside the engine's weight-for-age plausibility limits, so a typing slip is not read as growth faltering), `reference_unverified` (girls 3 to 6 months), `outside_reference_ages` (past the engine's last day, 1856, or a gap in the table).
- D163 (reference status superseded by D164). The reference values are transcribed from a screenshot and were not checked against the handbook. Girls 3 to 6 months reads 21-21 in the screenshot (a range with equal ends), which looks like a source typing error, so that cell is null and the case is not assessed until someone checks. The length range at 0 to 3 months was read as one merged cell. A test holds an independent copy of the transcription so any later edit to the file shows up.

## Open issues from growth monitoring
- I59 (CLOSED 2026-11-09: Edison, a dietitian, checked every value against the handbook; girls 3 to 6 months really reads 21-21, handled in D164). WAS: Verify the R19 weight table against the handbook, especially girls 3 to 6 months, and confirm it is the right reference for Malawi under-5 children (it is a reference range for term infants and paediatric patients, not a Malawi or WHO velocity standard). Owner: Maria and Edison.
- I60 (DECIDED 2026-11-09 by Edison as a dietitian: keep 28 days, D171). WAS: `MIN_INTERVAL_DAYS = 28` is an engineering choice, not from the reference. Scales that read to 0.1 kg make short intervals noisy (a 100 g error over 14 days is 7 g/day, as wide as the older-age ranges). Infants weighed weekly will get `interval_too_short`. Maria to confirm the interval, or give a clinical rule.
- I61 (DECIDED 2026-11-09 by Edison: a flag suggests clinician review and sets nothing else, D170; wording verified by Edison 2026-11-09, D174). WAS: What a flag should trigger (counselling, earlier review, setting the CMAM `failure_to_gain_weight` finding) is clinical. The API sets nothing. Maria to decide, and to review the wording.
- I62 (PARTLY CLOSED 2026-11-09: weight-for-age change, length/height trend and head circumference are done, D165 to D169; preterm velocity, single-value head cut-offs and trends for BMI-for-age and MUAC are still not covered). WAS: Not covered, no source in hand: change in weight-for-age z-score across visits (the engine can compute z at both visits, but a "faltering" cut-off, such as a fall across a set number of SD, needs a cited definition), length or height faltering and stunting trend, head circumference, and preterm velocity (g/kg/d). Edison to name the source if wanted.
- I63. Hope's side: the gateway must store each child's last weight and age and send them as `previous_measurement`, and must handle the optional `growth_monitoring` field and its not-assessed reasons (see `docs/deployment/integration-guide.md`).

## Growth trends (`thanzi_screen.growth.trend`, 2026-11-09). Add-on to growth monitoring. For Edison and Maria to review
- D164 (Edison, 2026-11-09). R19 is verified: Edison, a dietitian, checked every value against the handbook. Girls 3 to 6 months really reads 21-21, a single value, so a range is derived: centred on 21 with a half-width of 4.0 g/day, the average of the half-widths of the girls rows either side (2-3 months: 3.5, 6-9 months: 4.5), giving 17 to 25. The file marks it `girls_derived`, the response carries `reference_derived: true`, and a below-range result for those ages adds a message saying the range was derived. This replaces D163's "not assessed" for that band. A test recomputes the range from its neighbours.
- D165 (Edison, 2026-11-09: use the new WHO sources). Z-score trends across two visits, for weight-for-age (R5), length/height-for-age (R4) and head circumference-for-age (R20), using the WHO tables and the technical guide (R21) as the basis. Stateless like D158. `previous_measurement` gains three optional keys: `length_height_cm`, `measure_position` (required with a length) and `hc_cm`. The current visit's existing `hc_cm` is reused on the under-5 route (it was preterm-only before, and is no longer reported as ignored when the earlier visit also has a head measurement). Response: `growth_monitoring.trends`, one entry per indicator that has a value at both visits (weight always, length and head only when both visits give them).
- D166. Rule for weight and length. Flagged when the z-score falls by 1.0 SD or more (a full band, so it always crosses a line), or newly falls below -2 or -3 (the guide's alert and severity cut-offs: below -2 stunted or underweight, below -3 severe). A rise is reported (`direction: rose`) and never flagged here: weight gain faster than length is a weight-for-length question, which the engine already answers at each visit. `lines_crossed` lists the whole lines from -3 to +3 between the two values. A child already below -2 who stays there is not flagged for that alone. A z-score of exactly -2.0 counts as not below -2.
- D167. Rule for head circumference. Flagged for a change of 1.0 SD or more in either direction (a fall or a rise can matter). No single-value cut-off: the guide gives none for head size, so a value below -2 or above +2 is not flagged on its own. The WHO table ends at 60 months, so later ages are `outside_reference_ages`. The weekly table is used up to day 91 and the monthly table after, with linear interpolation; the two tables differ by under 0.2 cm at the hand-over (tested).
- D168. The 1.0 SD fall is an engineering choice. The guide says a plotted line that crosses a z-score line is a warning sign but gives no number of SD; 1.0 is the width of one band, so a flagged fall always crosses at least one line. See I64.
- D169. Not assessed, with a reason, for each trend: `interval_too_short` (under 28 days, D171), `implausible_measurement` (a z-score outside the engine's limits, so a typing slip is not read as a trend: weight -6 to +5 and length -6 to +6 are the engine's, head size -5 to +5 is a choice, I65), `outside_reference_ages`, `oedema_weight_unreliable` (current visit has oedema: WHO does not use weight z-scores then; length and head are unaffected). A length converted by the engine's 0.7 cm rule is used the same way here (tested equal to the engine).
- D170 (Edison, 2026-11-09: flag plus suggest clinician review). Any flag (weight gain below range, or any trend flag) sets `review_suggested: true` and `review_note` "A clinician should review this child's growth." No CMAM finding is set, no referral is recommended, and classification, tier, reasons, review and ML flags are unchanged (D9, tested over 32 combinations of record, earlier visit and view). This closes I61; Edison verified the wording on 2026-11-09 (D174).
- D171 (Edison, 2026-11-09, as a dietitian: no need to wait for Maria). Keep the 28-day minimum between visits for weight gain and all trends: at a scale resolution of 0.1 kg a shorter gap can make normal gain look like faltering, and under-five clinics usually see a child about monthly. This closes I60.
- D172 (Edison, 2026-11-09: could not find a preterm source; decision left to the developer). Preterm and corrected-age babies stay "not run, with a warning". No corrected-age rule is invented for growth monitoring. The engine already screens corrected-age babies on corrected age (approved 24-month end, provisional for 32 to under 37 weeks); turning trends on for them would also need the earlier visit's age corrected by the same offset, and the ASPEN reference has no preterm rows. See I67.
- D173. No separate "flat line" rule. A flat line in weight, length or head size drops against a rising median, so it shows up as a z-score fall; weight loss and low gain are already flagged by the velocity check. This keeps the guide's "stagnant line" without a new unsourced threshold.

- D174 (Edison, 2026-11-09: "I verify them", finish with the developer's judgement). Edison verified the 1.0 SD trend threshold (D168), the head circumference limits (D169), the derived girls 3 to 6 month range (D164) and the message wording. I64, I65, I66 and the wording part of I61 are closed. The tool is still advisory decision support, still not validated on real children, and a clinician still decides. I67 (corrected-age trends, needs a source), I68 (Hope's integration) and I69 (not covered) stay open.

- D175 (Edison, 2026-11-09: close the remaining items). I67 and I69 are closed as decisions to leave the work out of this release, not as solved: corrected-age trends (no source), preterm velocity per kg, single-value head circumference cut-offs, and BMI-for-age and MUAC trends (no cited cut-offs or tables; WHO arm-circumference tables, R8, are not held). Preterm and corrected-age babies keep the "not run" warning (D172). I68 is closed on our side only: the contract and guide are delivered, and Hope's confirmation is not in hand. Any of these reopens when its source or confirmation arrives.

## Open issues from growth trends
- I64 (CLOSED 2026-11-09: Edison verified the 1.0 SD threshold). WAS: Confirm the 1.0 SD fall as the flag threshold (D168), or give a clinical rule. It is the width of one z-score band, not a published cut-off. Owner: Maria and Edison.
- I65 (CLOSED 2026-11-09: Edison verified the -5 to +5 limits). WAS: Head circumference plausibility limits of -5 to +5 are my choice (I believe the WHO Anthro software uses the same, but it was not checked). Weight and length use the engine's.
- I66 (CLOSED 2026-11-09: Edison verified the derived range of 17 to 25 g/day). WAS: The derived girls 3 to 6 month range (17 to 25 g/day, D164) is arithmetic on the neighbouring rows, not a published range. If the handbook or a clinician gives a range for that age, replace it in `aspen_weight_velocity.json`; the test that recomputes it will then need updating.
- I67 (CLOSED 2026-11-09 by decision, not resolved: out of scope for this release; reopen if a source is supplied). WAS: Trends for corrected-age babies are off (D172). To turn them on: a source for the growth reference at corrected age, then correct the earlier visit's age by the same offset the engine uses, then decide the end age. Edison to send a source if wanted.
- I68 (CLOSED ON OUR SIDE 2026-11-09: the integration guide section 7 and the OpenAPI contract are delivered. Hope has NOT confirmed the gateway work; that is tracked with Hope, outside this repo). WAS: Hope's side: the gateway should also send the earlier visit's length (with how it was measured) and head circumference when it holds them, send `hc_cm` on this visit, and show `trends`, `review_suggested` and `review_note` (integration guide section 7). A client with a strict response schema must accept the new keys.
- I69 (CLOSED 2026-11-09 by decision: these stay out of scope until a cited cut-off or table exists; listed in docs/modules/growth.md). WAS: Still not covered: preterm velocity per kg, single-value head circumference cut-offs, BMI-for-age and MUAC trends. WHO arm-circumference tables are not held (R8).
