# Test report, release candidate 0.7.0 (Not Validated)

Decision support only. This report says what was run, where, and what was **not** tested. Nothing here is a clinical validation.

## Environment
- Build environment: Linux x86-64, 1 vCPU (Intel Xeon 2.1 GHz), 4 GB RAM. No Docker, no GitHub Actions, no UniPod access.
- Python 3.11.18 and 3.12.3. Dependencies as pinned in `constraints.txt` (D98).
- Date: 2026-11-07. Rule set `rules_v2016`. Engine `0.7.0`.

## Results run in the build environment
| Area | What was run | Result |
|---|---|---|
| Full suite | `pytest` with API tests required, Python 3.11 and 3.12 | 591 passed, 2 expected failures (I28 markers), 0 failed (590 on the first GitHub run, before the Dockerfile test was added). After the I28 fix (D106), Python 3.12 in the build environment: 709 passed, 0 expected failures, 0 failed (the new tests cover tiny lengths across ages and positions); Python 3.11 and the coverage figure are for GitHub CI to confirm |
| Coverage | `coverage` with branch coverage, reported only (Q3) | 98% overall (1962 statements, 514 branches). Lowest: `data/validate.py` 80%; all others 95% or more |
| Rule traceability | A plugin records which test makes each rule fire | All 23 rules exercised by at least one test (`traceability.md`) |
| Property tests | 8 invariants on the full pipeline: lower MUAC, lower weight, higher oedema grade never less urgent; danger sign or complication never lowers urgency or leads to outpatient care; missing information never lowers urgency; output invariants over 5,000+ inputs | All pass. No defect found |
| Robustness | About 190 hostile and malformed requests: bad JSON, wrong types, NaN and infinity, huge numbers, long strings, nested bodies, wrong methods and content types, duplicate headers, query abuse | One defect, I28 (below). Everything else returns 4xx with no echo and no trace |
| Black-box smoke | `scripts/smoke_api.py`, 19 checks, against a local uvicorn server with the real models | 19 passed. Includes: worker view identical for HIV true, false and not given |
| Dependency audit | `pip-audit` on the pinned set | No known vulnerabilities (2026-11-07) |
| Secret scan | gitleaks 8.30.1 over all 19 commits | 1 match: the throwaway test keys in the Phase 6 CI file. Allowlisted exactly and explained (D99). No other findings |
| Workflow lint | `actionlint` 1.7.12 with shellcheck on both workflows | Clean |
| Case pack | 65 synthetic scenarios through the engine | Regenerates identically (`--check`) |

## Load and resource measurements (build environment, not UniPod)
Single uvicorn worker, models loaded, no access log, client on the same single vCPU (so the client competes with the server). 2,000 requests each, mixed payloads, worker view.

| Concurrency | Throughput | Latency median | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 1 | 551 requests/s | 1.7 ms | 2.6 ms | 2.8 ms | 0 |
| 4 | 667 requests/s | 5.8 ms | 7.8 ms | 9.3 ms | 0 |
| 16 | 787 requests/s | 19.9 ms | 24.7 ms | 37.5 ms | 0 |

Startup to first healthy response: 0.43 s. Memory: 48 MB at start, 54 MB after 6,000 requests. These are measurements, not targets: no pass or fail threshold exists until Hope and UniPod provide expected load and server specifications (Q5, D97). Image size was not measured (no Docker here).

## Findings
- **I28 (fixed, D106):** a `length_height_cm` extremely close to zero, or small enough to go to zero or below after the 0.7 cm conversion, made the engine raise `ValueError`; the API returned a generic 500 instead of 422. No data was exposed. The engine now raises `InputError` and the API returns 422. The two expected-failure markers are replaced by regression tests.
- **I31 (wording, for Maria):** z-scores are shown to two decimals, so a child at -2.004 is classified moderate while the text says "-2.00 is from -3 up to -2".
- **I29:** keys are environment variables only; readable by `docker inspect`.
- The first scan of history flagged the Phase 6 CI test keys (D99).
- **Trivy on GitHub (D104):** two HIGH findings in the Debian base image's `zlib1g`, both with fixes available. Dockerfile now applies OS security updates at build time.

## Not tested (read this)
- **The release workflow has not run yet** (first run is the `v0.7.0` tag). The container smoke steps passed on `main` per Edison (not seen by the assistant). GitHub has run the other jobs (D104): tests, coverage, traceability, OpenAPI, case pack, `pip-audit` and gitleaks passed; the image built; Trivy then failed the build on two fixable HIGH findings in the base image's zlib1g, fixed by an OS update step in the Dockerfile that the next run must confirm. The smoke script itself passed 19 checks against a local server (I30).
- **Not run on UniPod servers or any target hardware.** Load numbers do not transfer.
- **No clinical validation.** The engine matches the encoded CMAM 2016 rules. Whether the rules and wording are right for practice is Maria's review of `case-pack.xlsx` (I18, I23, I10).
- **No real or Ministry data.** Machine-learning flags are trained on synthetic data; accuracy, fairness across districts, age and sex, and real recording errors are untested (I14, I15).
- **I5:** no cross-check against WHO Anthro software output yet (needs sample output from Edison).
- **Network isolation, TLS, rate limiting, audit logging** are deployment properties, not testable from code (I21).
- **Multi-worker or multi-container load**, long soak tests, memory over days, and failure injection on a real host.
- Compose example not run on a Docker host.

## Sign-off checklist (owner, status)
| Item | Owner | Status |
|---|---|---|
| CI run on `main` green, including the Docker job (Trivy and container smoke) | Edison | Green on `main` 2026-11-08 per Edison (D104, D105) |
| Case pack reviewed; agreement and comments returned | Maria | Pending |
| Worker wording confirmed, including neutral MAM text and exact-boundary z display (I18, I23, I31) | Edison (dietitian review, D106); Maria if available | Pending |
| Referral slip wording replaces placeholders (I10) | Maria / MoH | Pending |
| Decide I28 fix | Edison | Done: fix and regression tests (D106) |
| Network isolation of the API (I21) | Hope | Pending |
| Who holds the audit key, and how (I24) | Hope / Edison | Pending |
| Load probe on UniPod hardware; set targets | Hope | Pending |
| File-based keys (I29) | Edison / Hope | Decided: no, environment-based secrets (D106) |
| MUAC tables R8 and prevalence R9 (I12, I13) | Edison | Pending uploads |
| WHO Anthro cross-check sample (I5) | Edison | Pending |
| Chichewa translation (I19) | Owner per D34 | Pending |
| Real-data revalidation, fairness testing (I14, I15) | Team with MoH | Not started |

## Reproduce
    pip install -c constraints.txt -e ".[dev,api]"
    THANZI_REQUIRE_API_TESTS=1 python -m coverage run -m pytest -q -p tests._trace_plugin
    python -m coverage report
    python scripts/build_traceability.py --check
    python scripts/export_openapi.py --check
    python scripts/build_case_pack.py --check
    python scripts/smoke_api.py --base-url http://127.0.0.1:8080 --gateway-key KEY --audit-key KEY
    python scripts/load_probe.py --base-url http://127.0.0.1:8080 --gateway-key KEY --concurrency 4 --requests 2000
