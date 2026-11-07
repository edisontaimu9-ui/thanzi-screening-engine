# Phase 0 specification

## Objective
Independent, modular screening engine for children 0-59 months in Malawi: WHO anthropometrics, CMAM-based classification and referral, AI-assisted risk flagging with explanations, and a FastAPI interface for Thanzi AI.

## Architecture (one-way dependencies)
1. `anthro`: LMS z-scores (WFL/H, later HFA/LFA, WFA), age handling, input validation.
2. `rules`: CMAM classification and referral; each rule carries source ID, page and tag.
3. `ml`: risk flagging only (Phase 4).
4. `explain`: attributions for ML output (Phase 5).
5. `api`: FastAPI service (Phase 6).

## Safety invariant
Rules decide classification and referral. ML can add a flag or escalate for review; it can never downgrade or override a rule. A test enforces this.

## Inputs (planned)
Sex, age (date of birth and measurement date, or age in days), weight (kg), length or height (cm) with measurement position, MUAC (cm, 6-59 months only), oedema grade (none, +, ++, +++), optional appetite test, danger signs, medical complications, optional HIV status.

## Outputs (planned)
Z-scores with table version, classification (low risk, MAM, SAM-OTP, SAM-inpatient), user-facing tier, referral text, rule IDs fired, warnings, and a "decision support, not diagnosis" statement.

## Data policy
Synthetic data first, seeded from published WHO distributions. Real data only after ethics and data-sharing approval. No identifiable patient information.

## Dependencies
Runtime: standard library, plus FastAPI and pydantic from Phase 6. Dev: pytest, openpyxl (table conversion only).

## Deployment
Docker-ready for UniPod servers (Phase 6-7).

Rule extraction and sources: `docs/references/register.md`. Decisions: `docs/decisions/decision-log.md`.
