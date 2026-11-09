# Thanzi Screening Engine

Stateless screening service for acute malnutrition in children under five (0 to 59 months), built for use in Malawi. It
classifies a child against the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, screens preterm and low-birth-weight babies, and returns
advisory data-quality and growth flags.

> **Decision support only. Not a diagnostic device.** A trained health worker makes every clinical decision.
> Release `0.7.0` is a release candidate that has **not** been clinically validated or run on real patient data.
> See [Known limitations](#known-limitations).

## Features

- WHO Child Growth Standards z-scores (weight-for-age, length/height-for-age, weight-for-length/height, head
  circumference-for-age) with the WHO adjusted method beyond ±3 SD.
- Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 classification and referral: low risk, MAM, SAM (outpatient, inpatient, assessment needed) or unable to
  classify. Every rule traces to a source and page.
- Preterm and low-birth-weight screening (Fenton 2025 growth data, Care of the Infant and Newborn (COIN), Malawi, 2017 rules) with hand-over to the under-five
  engine on corrected age.
- Advisory flags that never change a classification: recording-error detection (logistic and small neural network),
  a rules-based review check, and growth monitoring between two visits (weight gain and z-score trends).
- Plain-language worker summary and a full audit trace.
- Optional local language-model client (disabled by default) and a free-text note checker (library only).

## Principles

- Clinical rules (`rules/`) are separate from machine learning (`ml/`). Machine learning can add a flag or ask for a
  review. It never diagnoses and never overrides or downgrades a clinical rule.
- Missing information is never assumed normal. An unassessed finding stays "not assessed".
- No child identifiers are accepted, stored or logged. The service is stateless.
- Worker responses contain no HIV information and no programme for moderate cases. The audit view needs a second key.
- The engine uses only the Python standard library. The HTTP layer is the only runtime dependency set.

## Quick start

Requires Python 3.11 or 3.12.

```bash
pip install -c constraints.txt -e ".[dev,api]"
python -m pytest -q

export THANZI_GATEWAY_KEY=$(openssl rand -hex 24)
uvicorn --factory thanzi_screen.api.app:create_app_from_env --host 127.0.0.1 --port 8080
```

```bash
curl -s -H "X-Gateway-Key: $THANZI_GATEWAY_KEY" -H "Content-Type: application/json" \
  http://127.0.0.1:8080/v1/screen -d '{
    "sex": "male", "age_days": 500, "weight_kg": 9.5, "length_height_cm": 75.0,
    "measure_position": "length", "oedema": "none", "muac_cm": 12.0, "appetite": "passed",
    "danger_signs": [], "complications": [], "clinically_well_and_alert": true}'
```

The service refuses to start without `THANZI_GATEWAY_KEY`.

## API summary

| Route | Key | Purpose |
|---|---|---|
| `GET /health` | none | `ok` or `degraded` |
| `GET /version` | gateway | Engine, rule set and model versions |
| `GET /v1/about` | gateway | Versions, uptime and component state |
| `GET /v1/metrics` | gateway | Request counts and `/v1/screen` latency |
| `POST /v1/screen?view=worker` | gateway | Screen one child (default view) |
| `POST /v1/screen?view=audit` | gateway + audit | Full detail, may contain HIV information |
| `GET /v1/llm/health`, `POST /v1/llm/generate` | gateway | Only when `THANZI_LLM_ENABLED=1` |

Contract: [`docs/api/openapi.json`](docs/api/openapi.json). Details: [docs/modules/api.md](docs/modules/api.md).

## Repository layout

```
src/thanzi_screen/
  anthro/     WHO z-scores and reference tables
  rules/      Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 classification, review check
  preterm/    Preterm and low-birth-weight engine and routing
  growth/     Weight-gain and z-score trend monitoring
  ml/         Recording-error flags, neural network (dl), note checker (nlp)
  explain/    Worker summary and audit trace
  api/        FastAPI service, security, metrics
  schemas/    Request and response models (the API contract)
  llm/        Optional local language-model client
  data/       Synthetic data generator and validation
models/       Trained advisory models and model cards
deploy/       Example container configuration
docs/         Documentation
scripts/      Training, contract export, smoke test, load probe
tests/        Unit, property, robustness, API and safety tests
```

## Documentation

| Topic | Document |
|---|---|
| Architecture and data flow | [docs/architecture.md](docs/architecture.md) |
| Environment variables | [docs/configuration.md](docs/configuration.md) |
| API endpoints, requests, errors | [docs/modules/api.md](docs/modules/api.md) |
| Deployment runbook | [docs/deployment/runbook.md](docs/deployment/runbook.md) |
| Gateway integration | [docs/deployment/integration.md](docs/deployment/integration.md) |
| Security, validation, error handling | [docs/security.md](docs/security.md) |
| Monitoring and maintenance | [docs/operations.md](docs/operations.md) |
| Testing and rule traceability | [docs/testing/test-report.md](docs/testing/test-report.md), [docs/testing/traceability.md](docs/testing/traceability.md) |
| References and licences | [docs/references/register.md](docs/references/register.md) |
| Modules | `docs/modules/`: anthro, rules, preterm, growth, ml, dl, nlp, explain, data, llm |
| Model cards | [models/MODEL_CARD.md](models/MODEL_CARD.md), [models/DL_MODEL_CARD.md](models/DL_MODEL_CARD.md) |
| Changes | [CHANGELOG.md](CHANGELOG.md) |

## Known limitations

- **Not clinically validated.** The rules match the encoded Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 text and are tested for behaviour. Clinical
  review of the case pack (`docs/testing/case-pack.xlsx`) and worker wording is outstanding.
- **Machine-learning flags are trained on synthetic data only.** Real recording errors are messier. Accuracy and
  fairness across districts, ages and sexes are untested.
- **No cross-check against WHO Anthro software output** on real sample records.
- **Not load tested on target hardware.** Measurements come from a single-vCPU build host.
- **Network isolation, TLS, rate limiting and audit logging are deployment responsibilities.** The service speaks plain
  HTTP and must run on a private network behind a gateway.
- **Referral slip wording is a placeholder**, and the MUAC model used for synthetic data is a placeholder.
- **Only English wording** exists. Translation by stable code is the integrator's task.
- **Preterm and corrected-age babies are excluded from growth monitoring** and from the recording-error flags.

## Licence and data

No licence has been chosen for the code. `src/thanzi_screen/preterm/fenton2025_lms.json` is Fenton 2025 data under
CC BY-NC-ND 4.0 (attribution, non-commercial, no derivatives): do not edit it. WHO tables and the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 have
their own terms; see the [reference register](docs/references/register.md).
