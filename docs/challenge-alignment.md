# Challenge alignment and role split

## Challenge
AI for Public Good Challenge (UniPod Malawi, MUBAS, timbuktoo, UNDP). Brief 3: **AI-Assisted Malnutrition Screening**, Ministry of Health and Sanitation (R10). The team's work plan (R11) calls it Use Case 1. The brief describes the problem and does not prescribe a solution.

## Team (from the work plan, R11)
| Member | Role | Main responsibility |
|---|---|---|
| Edison Taimu (Team Leader) | Nutrition & AI Systems Lead | AI design, coordination and reporting. Owns this repository |
| Hope Kalitera | Systems Architecture & Information Systems Lead | Architecture, databases, backend and frontend, deployment, security |
| Maria Talimire | Nutrition & Clinical Validation Lead | Screening workflows, referral logic, clinical review of AI outputs |

## Scope decision (D31)
The work plan proposed extending the Chakudya Nutrition Registry (API and MCP server) and Thanzi Coach. **Reuse of existing projects was dropped by Edison because it added complexity.** This repository is therefore the independent screening engine, with no dependency on those projects (consistent with the standing rule). Where the work plan says "Chakudya API" or "Thanzi Coach", read "the independent engine and whatever interface Hope builds".

## Edison's responsibility (this repository)
- Anthropometric engine (Phase 1) and CMAM 2016 classification and referral rules (Phase 2): done.
- Synthetic data pipeline (Phase 3), risk-flagging ML (Phase 4), explainability (Phase 5), API packaging (Phase 6), testing and deployment readiness (Phase 7).
- Clinical safety: rules traced to references; AI never diagnoses or overrides a rule (D9); decision support only.
- Screening engine v0.1 sign-off (work plan Week 3: Edison accountable).

## Work plan deliverables and this repository
| Work plan item | Accountable | What this repo provides or needs |
|---|---|---|
| Screening and referral logic specification (Wk 2) | Maria | Phase 2 rules and `docs/specs/phase-2-spec.md`, with the decision log, for her clinical review and sign-off. Phase 2 was closed by Edison; Maria's review is a pending dependency |
| Screening engine v0.1 (Wk 3) | Edison | Phases 1-2 built; Phases 3-5 add synthetic data, AI flags, explanations |
| System design, architecture, deployment, security | Hope | `ClassificationResult` and `ClinicalInputs` as the interface; standard-library Python engine, Docker-ready |
| End-to-end screening, offline mobile web app | Hope (Edison responsible for engine side) | Engine package or Phase 6 API |
| WhatsApp channel | Dropped (D32, privacy policy) | None |
| Analytics dashboard, de-identification, aggregation by district, facility, community | Hope | Result records. Phase 3 synthetic data carries a coarse district field (D33) |
| Validation and testing report (Wk 6) | Maria | She tests the prototype (Edison, 2026-11-07). Test suites and rule traceability support this; agreement with clinical classification needs Ministry data |
| Plain-language explanations of contributing factors | Edison | Phase 5 |
| Data-sharing arrangement (Wk 1) | Edison (A, R) | Until agreed, synthetic data only |
| Local languages | NLP/AI technical team (not named), with Edison's clinical input | Chichewa dataset, language support, translation and testing are theirs. This repo supplies stable reason and warning codes to translate |
| Point-of-care nutrition guidance | Edison (Clinical Nutrition Lead) | Develop the guidance, validate recommendations, ensure clinical accuracy and alignment with Malawi guidelines. Not yet in a phase (D34). Approved Malawi sources only |

## Interface contract
`ClassificationResult` and its reason, warning and rule codes are the interface for Hope and Maria. Changes are logged in the decision log.

## Resolved (Edison 2026-11-07)
- WhatsApp channel dropped because of the privacy policy (D32).
- Synthetic data carries a coarse district field (D33).
- Maria Talimire tests the prototype.
- Edison is not responsible for the dashboard or the other team-owned items, except point-of-care nutrition guidance (D34).
- Local languages: NLP/AI technical team, with Edison's clinical input (D34).

## Open
- Point-of-care nutrition guidance is Edison's but has no phase yet. Needs the approved Malawi guidance documents (see D34) and a spec before any build.
