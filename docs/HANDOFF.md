# Handoff: read this first in any new chat

## Who and what
Edison Taimu, Team Leader and Nutrition & AI Systems Lead, Thanzi AI. Building an independent AI-assisted malnutrition screening engine for children under five in Malawi. Repo: github.com/edisontaimu9-ui/thanzi-screening-engine

## Role for the assistant
Senior ML Engineer, Clinical AI Systems Architect and Technical Mentor.

## Challenge
AI for Public Good Challenge, Brief 3 (AI-Assisted Malnutrition Screening, Ministry of Health). Team: Edison (engine, AI design), Hope Kalitera (architecture, backend/frontend, deployment, security), Maria Talimire (clinical validation). Chakudya/Thanzi Coach reuse (D31) and the WhatsApp channel (D32) were dropped. See docs/challenge-alignment.md.

## Standing rules
- New independent codebase. Do not reuse or depend on Chakudya Nutrition Registry, Thanzi Coach, Chakudya ML Laboratory or Chakudya MCP Server. No proprietary code or datasets.
- Check licences and IP before using any external resource.
- Synthetic data first. No identifiable patient data without authorisation.
- Clinical rules traceable to approved references. Never invent thresholds, formulas, reference values or datasets.
- AI never independently diagnoses or overrides clinical safety rules.
- Python, modular, unit tests for every calculation and classification rule, minimal dependencies, Docker-ready (UniPod servers).
- Per phase: objective, resources, review uploaded files, spec, WAIT for approval, implement only that phase, run tests and report, document, list outstanding issues, WAIT before next phase.
- Resource handling: identify references, check uploads, give official download links, otherwise ask for upload; record source, version, date, licence, intended use; separate documented requirements from assumptions and recommendations.

## Delivery preferences
Reply in English, terse. For each update: build on the existing repo, zip only changed files with a change-descriptive name, give the unzip command (zips are in the Download folder) and exact git add/commit/push commands. Work is done on Android/Termux.

## Phase status
- Phase 0: COMPLETE. docs/specs/phase-0-spec.md, docs/decisions/decision-log.md.
- Phase 1 (anthropometric engine): COMPLETE, approved by Edison 2026-11-07. 126 tests passing. See docs/modules/anthro.md.
- Phase 2 (CMAM classification and referral): COMPLETE, closed by Edison 2026-11-07. 203 tests passing. See docs/modules/rules.md, decision-log D16-D30. Only I10 (referral slip wording, placeholder) remains.
- Point-of-care nutrition guidance: owned by Edison (D34), not yet in a phase; needs approved Malawi sources and a spec first.
- Phase 3 (data engineering): COMPLETE, closed by Edison 2026-11-07. 229 tests passing. See docs/modules/data.md, decision-log D35-D44. Pending inputs: R8 (WHO MUAC tables), R9 (Malawi prevalence), district list check (D43).
- Phase 4 (advisory flags): COMPLETE, closed by Edison 2026-11-07. See docs/modules/ml.md, models/MODEL_CARD.md, decision-log D45-D57.
- Phase 5 (explainability): COMPLETE, closed by Edison 2026-11-07. 273 tests passing. See docs/modules/explain.md, decision-log D58-D73. Wording review pending (I18).
- Phase 6 (FastAPI packaging): COMPLETE, closed 2026-11-07 (D92) with CI #2 green on `b817e9c`. 374 tests passing in the build environment (Python 3.12). See docs/specs/phase-6-spec.md, docs/modules/api.md, decision-log D74-D92. I20 decided (D86): no programme and no HIV information in any worker response; real values in the audit view only. Open: I21 (Hope: network isolation), I23 (Maria: neutral MAM wording), I24 (Hope: audit key holder), I25 (D82-D84 confirmation).
- Phase 7 (testing and deployment readiness): COMPLETE, closed by Edison 2026-11-08 (D93-D105), CI green on `main`. Release candidate `0.7.0`, not validated. 591 tests passing plus 2 expected failures (I28) at close; I28 then fixed (D106), 709 tests passing in the build environment. Evidence in docs/testing/; deployment in docs/deployment/runbook.md and deploy/. `v0.7.0` tagged and released as a pre-release on 2026-11-08, release workflow green (D107). Decided 2026-11-08 (D106): I28 fixed, I29 no file-based keys. Open: I31 (Edison reviews the wording and case pack), I5 (waiting for sample WHO Anthro output), UniPod server specifications and network isolation (I21), and the sign-off list in docs/testing/test-report.md. Do not start Phase 8 without Edison's word.
- Local LLM client (add-on on branch `feat/llm-client`, 2026-11-08, proposed, not a phase): `thanzi_screen.llm` plus optional `/v1/llm/*` routes, off by default, independent of screening. See docs/modules/llm.md, decision-log D128-D134, open I43-I47. Needs Edison's review, a real-server run (I45) and model licence checks (I44) before any use.
- NLP for free-text notes (add-on, 2026-11-08, proposed, not a phase): `thanzi_screen.ml.nlp` (extract, cross-check, redact), advisory only, standard library, not wired into the API. See docs/modules/nlp.md, decision-log D135-D144, open I48-I52. Local LLM client merged to `main` (PR #5, CI green); I43 decided: keep the route, off by default.
- Growth monitoring (add-on, Edison's request, not a phase): `thanzi_screen.growth`. Weight-gain velocity against the ASPEN reference (R19, verified by Edison 2026-11-09; girls 3 to 6 months is a derived range, D164) and, from 2026-11-09, z-score trends across two visits for weight-for-age, length/height-for-age and head circumference (R4, R5, R20, guide R21). Advisory only, stateless (the caller sends `previous_measurement`), under-5 route, standard library. A flag suggests clinician review (D170). Preterm and corrected-age babies are skipped (D172). See docs/modules/growth.md, decision-log D157-D174. I59 to I69 closed (I67 and I69 by decision, D175; I68 on our side only, Hope has not confirmed the gateway work).
- Deep learning (add-on, 2026-11-08, not a phase): `thanzi_screen.ml.dl` (plain-Python neural network, presets tiny/small/base, hardware-aware, train and predict), standard library only. Switched on by Edison (D153): `ml_flags.deep_recording_error` beside the logistic flag in `POST /v1/screen`, advisory, synthetic data only, `THANZI_DEEP_ENABLED=0` turns it off. See docs/modules/dl.md, docs/deployment/deep-flag-integration.md and docs/deployment/integration-guide.md (for Hope), decision-log D145-D156, open I53-I55, I57, I58. Train with `python scripts/train_deep.py`.
- Run tests: `pip install -c constraints.txt -e ".[dev,api]" && python -m pytest -q` from the repo root. Release: push tag `v0.7.0` (see docs/release/v0.7.0.md).

## Open issues
See bottom of docs/decisions/decision-log.md.
