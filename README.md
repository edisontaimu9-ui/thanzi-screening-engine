# thanzi-screening-engine

Independent, modular under-five (0-59 months) malnutrition screening engine for Thanzi AI, Malawi.

**Status:** Phases 0 and 1 complete (Phase 1 approved 2026-11-07). Phase 2 spec drafted, awaiting approval. See `docs/HANDOFF.md` for the current state and how to continue.

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
scripts/     build_reference_tables.py, data generation
```

## Phases
0 Discovery and spec (done) | 1 Anthropometrics (done) | 2 Clinical classification (spec drafted) | 3 Data engineering | 4 ML | 5 Explainability | 6 FastAPI packaging | 7 Testing and deployment readiness

Licence: not yet chosen.

## Quick start
```
pip install pytest
python -m pytest -q
```
See `docs/modules/anthro.md`.
