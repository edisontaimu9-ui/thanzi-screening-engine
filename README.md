# thanzi-screening-engine

Independent, modular under-five (0-59 months) malnutrition screening engine for Thanzi AI, Malawi.

**Status:** Phases 0 and 1 complete (Phase 1 approved 2026-11-07). Phase 2 (CMAM classification) closed 2026-11-07. Phase 3 (synthetic data) closed 2026-11-07. Phase 4 (advisory ML flags) closed 2026-11-07. Phase 5 (explainability) closed 2026-11-07. Phase 6 (FastAPI packaging) implemented 2026-11-07; closes when CI is green on `main`. See `docs/HANDOFF.md` for the current state and how to continue.

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
