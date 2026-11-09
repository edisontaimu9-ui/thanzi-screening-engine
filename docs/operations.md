# Monitoring and maintenance

## Health

- `GET /health` needs no key and returns only `{"status": "ok"}` or `"degraded"`. `degraded` means the logistic model
  files are missing or mismatched. Screening continues with rules only. `/health` does not reflect the neural-network
  flag or the language-model client.
- The image has a built-in health check (`docker inspect --format '{{.State.Health.Status}}'`).
- `GET /v1/about` (gateway key) reports the version and state of each component: `screening_engine`, `ml_logistic`,
  `ml_deep`, `growth_monitoring`, `llm_service`.
- `GET /v1/metrics` (gateway key) reports `since`, `uptime_seconds`, `requests_total`, `server_errors`, `by_route`,
  `by_status` and `screen_latency` (`p50_ms`, `p95_ms`, `max_ms`, `mean_ms`, over the last 1,000 `/v1/screen` calls).
  Refused calls (401, 413) are counted. It holds counts and durations only. Counters are in memory, reset on restart,
  and each worker process counts its own requests, so the gateway should store readings if it needs history and compute
  rates from the difference between two readings.
- `GET /v1/llm/health` gives live language-model state when that feature is enabled.

## What to track and alert on

| Signal | Source | Action |
|---|---|---|
| Availability | Poll results for `/health` and `/v1/about` | Alert on failure |
| `health` or any component `degraded` | `/v1/about` | Alert. Check model files and `THANZI_MODELS_DIR` |
| Rise in `server_errors` or 5xx | `/v1/metrics` | Alert |
| Rise in 401 | `by_status` | Key fault or misconfigured client |
| Rise in 422 | `by_status` | Data-entry or gateway bug |
| `screen_latency.p95_ms`, `max_ms` | `/v1/metrics` | Investigate large rises (median was about 2 ms on a 2.1 GHz vCPU) |
| Fall in `uptime_seconds` between readings | `/v1/metrics` | Service restarted, counters reset |
| Version change not tied to a release | `/v1/about` | Investigate |
| Flag and `review_suggested` rates per facility | Gateway's stored results | Review for systematic measuring or typing problems |

Poll every 30 to 60 seconds and cache the answer. Do not use `/v1/screen` as a health check.

## Logs

Logs hold no keys and no request values (checked in CI). They hold access lines (client address, path, status) and error
types. A log line mentioning the HIV scan indicates a bug and should be reported. If the gateway logs requests, those
logs are health data.

## Routine maintenance

- **Dependencies:** Dependabot opens pull requests for GitHub Actions, the Docker base image and pip. CI runs
  `pip-audit`, Trivy and gitleaks on every change. Re-check licences and re-run the audit at each release. Regenerate
  pins with `scripts/refresh_constraints.py`.
- **Contract:** after any API change run `python scripts/export_openapi.py`. CI fails if the committed contract is stale.
- **Case pack and traceability:** regenerate with `python scripts/build_case_pack.py` and
  `python scripts/build_traceability.py`. CI fails if they drift or if any rule has no test.
- **Models:** retrain only from a verified synthetic dataset with `scripts/generate_synthetic.py`,
  `scripts/train_models.py` and `scripts/train_deep.py`. Training refuses unverified or non-synthetic data. Retrain and
  re-review when real prevalence figures and WHO MUAC-for-age tables are adopted.
- **Reference data:** tables carry SHA-256 checksums in `MANIFEST.json`. Do not edit `fenton2025_lms.json`.
- **Releases:** push a tag `vX.Y.Z`. The release workflow builds and tests the image and publishes a pre-release with the
  image tarball, SBOMs, checksums and test evidence. Registry publishing is a deployment decision.

## Incident basics

| Symptom | Likely cause | Action |
|---|---|---|
| Service will not start | Missing, short or duplicated key | Check `THANZI_GATEWAY_KEY` and `THANZI_AUDIT_KEY` |
| `/health` is `degraded` | Model files missing or mismatched | Restore `models/`, check `THANZI_MODELS_DIR`, restart |
| 401 from the gateway | Key mismatch | Compare the gateway's key with the container's |
| 403 on the audit view | Audit key wrong, or audit disabled | Set `THANZI_AUDIT_KEY` and use both headers |
| Unexpected 500s | Defect | Collect the error type from the logs (never the input), roll back, report |
| Deep flag missing | Disabled or files missing | Check `THANZI_DEEP_ENABLED` and `/v1/about` `ml_deep` |

Rollback: see the [runbook](deployment/runbook.md).
