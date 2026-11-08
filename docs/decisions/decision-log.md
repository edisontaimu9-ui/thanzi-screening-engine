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
- D115. The ML recording-error flag is not run on the corrected-age route (models trained on chronological ages).

## Open issues from the preterm integration
- I32. follow_up has no under-5 tier. Default follow_up -> mam over-refers late-preterm LBW babies who only need weekly review; follow_up -> low_risk would hide facility-KMC and unsupervised-home-care babies. Clinician to choose; one line in `routing_config.json`.
- I33. The brief gives the corrected-age end (age 3) only for GA under 32 weeks. 24 months for 32 to under 37 weeks is a placeholder.
- I34. Term babies under 2500 g (GA 37 or more) are routed to preterm under 50 weeks PMA but get chronological age afterwards, not the brief's literal formula (at most 3 weeks of correction). Confirm.
- I35. Mapping under-5 inputs to preterm triggers: hypoglycaemia (any) -> "not correcting"; severe_dehydration -> dehydrated; any danger sign or complication -> sick (refer); failure_to_gain_weight true -> 0 gaining days; unconsciousness counts as lethargic.
- I36. Preterm and corrected-age routes require the under-5 fields `length_height_cm`, `measure_position` and `oedema`, though the preterm engine treats length as optional. Make them conditional?
- I37. Born under 2500 g with gestational age unknown: under-5 flow with a warning, no preterm screen. GA is often unknown in clinics; confirm, or define a fallback.
- I38. Oedema on the preterm route raises the level to refer (never urgent). The preterm engine does not read oedema.
- I39. The under-5 engine uses "failure to gain weight" (CMAM Table 5 text and the `failure_to_gain_weight` field), which conflicts with the "faltering, never failure" rule on the corrected-age route. Not changed. Display-only rename?
- I40. In `engine.py`, the urgent-trigger set and the "not gaining" age (`> 14`) are hardcoded; the file's `min_age_days` is used only by the growth block. Tags in `preterm_rules.json` document but do not drive them. Logic left as supplied.
- I41. Corrected age applies CMAM thresholds (MUAC from 6 months, the infant criteria) to corrected age. Confirm.
- I42. No Docker build was run in this environment (CI does it). Data shipping was checked with a clean non-editable install.
