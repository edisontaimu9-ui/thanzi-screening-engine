# thanzi-screening-engine

Independent, modular under-five (0-59 months) malnutrition screening engine for Thanzi AI, Malawi.

**Status:** Phases 0 and 1 complete (Phase 1 approved 2026-11-07). Phase 2 (CMAM classification) closed 2026-11-07. Phase 3 (synthetic data) closed 2026-11-07. Phase 4 (advisory ML flags) closed 2026-11-07. Phase 5 (explainability) closed 2026-11-07. Phase 6 (FastAPI packaging) closed 2026-11-07. Phase 7 (testing and deployment readiness) closed 2026-11-08 as release candidate 0.7.0, **not validated**. See `docs/HANDOFF.md` for the current state and how to continue.

## Principles
- Independent codebase: no dependency on, or reuse of, any other project's code or data.
- Clinical rules (`rules/`) are separate from machine learning (`ml/`).
- Every clinical rule traces to a reference in `docs/references/register.md`.
- AI may add flags or escalate for review. It never diagnoses, and never overrides or downgrades a clinical rule.
- Synthetic data only until ethics and data-sharing approval exists.
- Decision support only; not a diagnostic device.

## Layout
```
docs/        HANDOFF.md, specs/, references/, decisions/
src/thanzi_screen/  anthro/ rules/ ml/ explain/ api/ schemas/
data/        synthetic/
tests/       anthro/ rules/ ml/ api/ safety/
scripts/     build_reference_tables.py, data generation, export_openapi.py
```

## Phases
0 Discovery and spec (done) | 1 Anthropometrics (done) | 2 Clinical classification (done) | 3 Data engineering (done) | 4 ML flags (done) | 5 Explainability (done) | 6 FastAPI packaging (implemented, CI pending) | 7 Testing and deployment readiness

Licence: not yet chosen.

## Quick start
```
pip install pytest
python -m pytest -q
```
See `docs/modules/anthro.md`, `docs/modules/rules.md`, `docs/modules/data.md`, `docs/modules/ml.md`, `docs/modules/explain.md`.

## Run the API (Phase 6)
```
pip install -e ".[dev,api]"
THANZI_GATEWAY_KEY=<16+ characters> uvicorn --factory thanzi_screen.api.app:create_app_from_env
python -m pytest -q
```
No gateway key, no start. Run it behind Hope's gateway on a private network. Details and the deployment checklist: `docs/modules/api.md`. Contract: `docs/api/openapi.json`.

## Testing, security checks and release (Phase 7)
Release candidate `0.7.0`, **not validated**. Evidence: `docs/testing/test-report.md` (what was run, what was not), `docs/testing/traceability.md` (every CMAM rule and its tests), `docs/testing/case-pack.xlsx` (synthetic scenarios for clinical review). Deployment: `docs/deployment/runbook.md`, `deploy/docker-compose.example.yml`. Tools: `scripts/smoke_api.py`, `scripts/load_probe.py`. Install with `pip install -c constraints.txt -e ".[dev,api]"`.

## Preterm and low-birth-weight babies
`POST /v1/screen` routes by two optional fields, `gestational_age_weeks` and `birth_weight_g` (grams). Full detail: `docs/modules/preterm.md`.

**Routing rules.** Born under 37 weeks or under 2500 g, and under 50 weeks post-menstrual age (PMA = gestational age + chronological age): the preterm engine (Fenton 2025 z-scores, COIN 2017 Malawi rules). From 50 weeks PMA: the under-5 engine on corrected age (chronological age minus (40 - GA) weeks), kept until age 3 if GA is under 32 weeks (24 months for 32 to under 37 weeks is a proposed placeholder). Without the two fields nothing changes.

**Level mapping** (one table in `routing_config.json`; no new levels):

| Preterm level | Under-5 tier |
|---|---|
| routine | low_risk |
| follow_up | mam (proposed) |
| refer | mam |
| urgent_refer | urgent |

Only danger signs give `urgent_refer`. Faltering growth is never called from one percentile: it needs a z-score decline from birth, after 14 days of age.

**Data licence.** `src/thanzi_screen/preterm/fenton2025_lms.json` is Fenton 2025 data, CC BY-NC-ND 4.0 (attribution, non-commercial, no derivatives). Do not edit it. Responses carry the attribution.

**Needs clinician sign-off:** the level map (follow_up), z-decline tiers, the [proposed] urgent triggers, the corrected-age end point for 32 to under 37 weeks, oedema handling and the input mapping. Release candidate, not validated.
