# Handoff: read this first in any new chat

## Who and what
Edison Taimu, Team Leader and Nutrition & AI Systems Lead, Thanzi AI. Building an independent AI-assisted malnutrition screening engine for children under five in Malawi. Repo: github.com/edisontaimu9-ui/thanzi-screening-engine

## Role for the assistant
Senior ML Engineer, Clinical AI Systems Architect and Technical Mentor.

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
- Phase 0: COMPLETE. See docs/specs/phase-0-spec.md and docs/decisions/decision-log.md.
- Phase 1 (anthropometric engine): spec proposed, NOT approved, no code yet.
  - Pending decisions: (1) interpolate L, M, S between 0.5 cm table rows or use nearest row; (2) extreme z-scores: plain z-score plus flag, verify WHO adjusted method before including; (3) include weight-for-age and height/length-for-age in Phase 1.
  - Files still needed if (3) is yes: WHO Expanded tables (xlsx, z-scores, boys and girls) for length/height-for-age and weight-for-age.
  - Already held by Edison (not in git): WHO WFL/WFH z-score xlsx x4, WHO expanded-tables instructions PDF, Malawi CMAM 2016 PDF.

## Open issues
See bottom of docs/decisions/decision-log.md.
