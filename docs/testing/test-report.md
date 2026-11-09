# Test report, release candidate 0.7.0 (not validated)

Decision support only. This report states what was run, where, and what was **not** tested. Nothing here is a clinical
validation.

## Environment

- Linux x86-64, Python 3.12.3. CI also runs Python 3.11. Dependencies as pinned in `constraints.txt`.
- Rule set `rules_v2016`. Engine `0.7.0`.
- Load and security measurements below were recorded on a 1 vCPU (Intel Xeon 2.1 GHz), 4 GB RAM build host with no Docker
  and no access to target hardware. Re-run them at each release.

## Results

| Area | What was run | Result |
|---|---|---|
| Full suite | `pytest` with API tests required (`THANZI_REQUIRE_API_TESTS=1`) | 1,409 passed, 0 failed |
| Coverage | `coverage` with branch coverage, reported only (no gate) | 98% overall (4,270 statements, 1,162 branches). Lowest: `data/validate.py` 80%, `ml/nlp/lexicon.py` 84% |
| Rule traceability | A plugin records which test makes each rule fire | All 23 rules exercised by at least one test ([traceability.md](traceability.md)) |
| Property tests | Invariants over the full pipeline: lower MUAC, lower weight or a higher oedema grade is never less urgent; a danger sign or complication never lowers urgency or leads to outpatient care; missing information never lowers urgency; output invariants over 5,000+ inputs | All pass |
| Robustness | About 190 hostile and malformed requests: bad JSON, wrong types, NaN and infinity, huge numbers, long strings, nested bodies, wrong methods and content types, duplicate headers, query abuse | Every case returns 4xx with no echo of values and no trace |
| Black-box smoke | `scripts/smoke_api.py`, 19 checks against a local server with the real models | 19 passed, including a worker view identical for HIV true, false and not given |
| Dependency audit | `pip-audit` on the pinned set | No known vulnerabilities when last run (2026-11-07). CI re-runs it on every change |
| Secret scan | gitleaks over the full history | One allowlisted match: throwaway test keys in an early CI file. No other findings |
| Workflow lint | `actionlint` with shellcheck on both workflows | Clean |
| Image scan | Trivy in CI | Two fixable HIGH findings in the Debian base image's `zlib1g` were fixed by applying OS security updates at build time |
| Case pack | 65 synthetic scenarios through the engine | Regenerates identically (`--check`) |

## Load and resource measurements (build host, not target hardware)

Single uvicorn worker, models loaded, no access log, client on the same single vCPU (so the client competes with the
server). 2,000 mixed requests each, worker view.

| Concurrency | Throughput | Median | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 1 | 551 requests/s | 1.7 ms | 2.6 ms | 2.8 ms | 0 |
| 4 | 667 requests/s | 5.8 ms | 7.8 ms | 9.3 ms | 0 |
| 16 | 787 requests/s | 19.9 ms | 24.7 ms | 37.5 ms | 0 |

Startup to first healthy response: 0.43 s. Memory: 48 MB at start, 54 MB after 6,000 requests. These are measurements,
not targets. No pass or fail threshold exists until the expected load and server specification are known.

## Findings

- **Fixed:** a `length_height_cm` extremely close to zero, or small enough to reach zero or below after the 0.7 cm
  convention conversion, raised an uncaught error and returned a generic 500. The engine now raises `InputError` and the
  API returns 422. Regression tests cover tiny lengths across ages and positions.
- **Wording:** z-scores are shown to two decimals, so a child at -2.004 is classified moderate while the text reads
  "-2.00 is from -3 up to -2". This is correct but looks contradictory at an exact boundary. For clinical wording review.
- **Secrets:** keys are environment variables only and are readable by anyone who can run `docker inspect` on the host.

## Not tested

- **Not run on target servers or hardware.** Load numbers do not transfer.
- **No clinical validation.** The engine matches the encoded Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 rules. Whether the rules and wording are right for
  practice requires clinician review of `case-pack.xlsx`.
- **No real or Ministry data.** ML flags are trained on synthetic data. Accuracy, fairness across districts, ages and
  sexes, and real recording errors are untested.
- **No cross-check against WHO Anthro software output** on real sample records.
- **Network isolation, TLS, rate limiting and audit logging** are deployment properties and cannot be tested from code.
- **Multi-worker or multi-container load**, long soak tests, memory over days and failure injection on a real host.
- **Container examples** (`deploy/`) have not been run on a Docker host, and the language-model client has been tested only
  against fake loopback servers.
- **Release artefacts:** the published image tarball has not been loaded and run on a Docker host from a download, and
  checksums have not been verified against a download.

## Sign-off checklist

| Item | Owner | Status |
|---|---|---|
| CI green on `main`, including the Docker job (Trivy and container smoke) | Maintainers | Green when last run |
| Case pack reviewed, agreement and comments returned | Clinical reviewer | Pending |
| Worker wording confirmed, including neutral wording for moderate cases and exact-boundary z display | Clinical reviewer | Pending |
| Referral slip wording replaces placeholders | Clinical reviewer / Ministry of Health | Pending |
| Network isolation of the API | Platform owner | Pending |
| Audit-key holder and access logging | Platform owner / clinical lead | Pending |
| Load probe on target hardware, targets set | Platform owner | Pending |
| WHO MUAC-for-age tables and published prevalence figures for the data generator | Maintainers | Pending |
| WHO Anthro cross-check sample | Maintainers | Pending |
| Local-language translation of the message catalogue | Language team | Pending |
| Real-data revalidation and fairness testing | Maintainers with the Ministry of Health | Not started |

## Reproduce

```bash
pip install -c constraints.txt -e ".[dev,api]"
THANZI_REQUIRE_API_TESTS=1 python -m coverage run -m pytest -q -p tests._trace_plugin
python -m coverage report
python scripts/build_traceability.py --check
python scripts/export_openapi.py --check
python scripts/build_case_pack.py --check
python scripts/smoke_api.py --base-url http://127.0.0.1:8080 --gateway-key KEY --audit-key KEY
python scripts/load_probe.py --base-url http://127.0.0.1:8080 --gateway-key KEY --concurrency 4 --requests 2000
```
