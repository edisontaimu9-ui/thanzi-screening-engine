# Local LLM client (`thanzi_screen.llm`)

Status: **proposed add-on, not a numbered phase**. Built on branch `feat/llm-client` at Edison's request (2026-11-08). Decisions D128 to D134, open issues I43 to I47 in `docs/decisions/decision-log.md`. Off by default. Not validated on real hardware (I45).

## What it is, and what it is not
A small async client that sends text to a **local** language model server (Ollama, llama.cpp, or any OpenAI-compatible server) and returns text. It exists so later features (for example, drafting plain-language wording for clinician review) can use a small model such as Qwen without the screening engine knowing which model, server or provider is behind it.

It is **not** part of screening. The model's text is never an input to classification, referral, flags or explanations. The screening code does not import it, it does not import the screening code, and tests fail if either changes (D128).

## Layout
```
src/thanzi_screen/llm/
  config.py      LLMConfig, THANZI_LLM_* loading, endpoint privacy check
  types.py       Message, GenerationParams, GenerationResult, HealthStatus
  errors.py      LLMError and subclasses (fixed messages, stable codes)
  base.py        LLMProvider (contract), TextGenerator (what callers depend on)
  client.py      LLMClient: concurrency limit, deadline, retry, clean-up, health
  http.py        the only httpx user (lazy import)
  text.py        strip_reasoning (<think> blocks)
  providers/     ollama, llamacpp, openai_compat, mock, and the registry
src/thanzi_screen/api/llm_routes.py   optional HTTP routes (only when enabled)
```

## Use from Python
```python
from thanzi_screen.llm import LLMClient, LLMConfig, GenerationParams

config = LLMConfig(provider="ollama", endpoint="http://127.0.0.1:11434", model="qwen2.5:1.5b")
async with LLMClient(config) as llm:
    status = await llm.health()                      # never raises
    result = await llm.generate("Synthetic text only.", system="Answer in one sentence.",
                                params=GenerationParams(max_tokens=64, temperature=0.0))
    print(result.text, result.finish_reason, result.latency_ms)
```
Code that uses a model should depend on `TextGenerator` (in `base.py`), not on `LLMClient`, so a test double or a different implementation can be passed in.

## Use over HTTP (optional)
Set `THANZI_LLM_ENABLED=1` and the `THANZI_LLM_*` settings. Two routes then exist, both behind the gateway key like every route except `/health`:

| Route | Purpose |
|---|---|
| `GET /v1/llm/health` | 200 when the model server is usable (`ok` or `degraded`), 503 when `unavailable`. Body: state, provider, model, detail, model_available, latency_ms. No endpoint URL is returned. |
| `POST /v1/llm/generate` | Body: `prompt` (1 to 4000 characters), optional `system`, `max_tokens` (1 to 1024), `temperature` (0 to 2). Unknown fields are refused. Returns text, model, provider, finish_reason, latency_ms, token counts and a fixed `notice`. |

When the feature is off the routes do not exist (404) and `docs/api/openapi.json` is unchanged. `GET /health` (the container health check) ignores the model completely: a dead model server never changes a screening result or the screening health status (tested).

Error codes (`code` in the body): `llm_timeout` 504, `llm_busy` 503 (with `Retry-After`), `llm_unreachable` 503, `llm_model_not_found` 503, `llm_auth` 503, `llm_server_error` 503, `llm_bad_response` 502, `llm_rejected` 502, `llm_bad_request` 422. Messages are fixed strings: no prompt, reply, URL or server text.

## Providers
| `THANZI_LLM_PROVIDER` | Server | Wire format | Health check |
|---|---|---|---|
| `ollama` | Ollama | `POST /api/chat` | `GET /api/tags`: model present? (`degraded/model_not_found` if not) |
| `llamacpp` | llama.cpp `llama-server` | `POST /v1/chat/completions` | `GET /health` (503 while loading = `degraded/loading`) |
| `openai_compat` | LM Studio, vLLM, llama-cpp-python | `POST /v1/chat/completions` | `GET /v1/models`: model listed? |
| `mock` | none (in process) | none | always ok |

**Replacing a model:** change `THANZI_LLM_MODEL`. **Replacing the server:** change `THANZI_LLM_PROVIDER` and `THANZI_LLM_ENDPOINT`. **Adding a new kind of server:** subclass `LLMProvider` (two async methods: `generate` and `health`), call `register_provider("name", YourClass)`. None of these touch the screening engine.

## Settings
All are optional environment variables (full annotated list: `deploy/llm.env.example`). An invalid value stops start-up and names the variable, never its content.

| Variable | Default | Meaning |
|---|---|---|
| `THANZI_LLM_ENABLED` | off | Must be exactly `1` to mount the routes |
| `THANZI_LLM_PROVIDER` / `_ENDPOINT` / `_MODEL` | ollama / `http://127.0.0.1:11434` / `qwen2.5:1.5b` | Server and model. Endpoint is a base URL (a path prefix is allowed) |
| `THANZI_LLM_API_KEY` | none | Bearer token for servers that need one. Never logged or shown in a repr |
| `_CONNECT_TIMEOUT_S` / `_TIMEOUT_S` / `_HEALTH_TIMEOUT_S` | 3 / 60 / 2 | Connect, whole generation, health check |
| `_QUEUE_TIMEOUT_S` | 5 | Wait for a free slot before `llm_busy` |
| `_MAX_CONCURRENCY` | 1 | Parallel generations (1 to 8) |
| `_MAX_RETRIES` / `_RETRY_BACKOFF_S` | 1 / 0.5 | Transient errors only, exponential with jitter |
| `_MAX_PROMPT_CHARS` / `_MAX_RESPONSE_BYTES` | 8000 / 1 MiB | Input and reply caps |
| `_KEEP_ALIVE` | 5m | Ollama: how long the model stays in memory (`0` unloads at once) |
| `_THINK` | not sent | Ollama: `false` turns off Qwen3-style visible reasoning |
| `_STRIP_REASONING` | true | Remove `<think>...</think>` from any reply |
| `_MAX_TOKENS` / `_TEMPERATURE` / `_TOP_P` / `_TOP_K` / `_SEED` / `_CONTEXT_TOKENS` | 256 / 0.2 / unset / unset / unset / 2048 | Generation. Context size is honoured by Ollama only; llama.cpp fixes it with `-c` at start-up |
| `THANZI_LLM_ALLOW_REMOTE` | 0 | See Privacy |

## Privacy and security (D131)
- **Off by default**, and the route set is absent when off.
- **Local only by default.** The endpoint must be loopback, a private or link-local IP, `localhost`, a single-word name (a Docker service such as `ollama`) or end in `.internal`, `.local`, `.lan`, `.localdomain`, `.svc`. Anything else is refused at start-up. A remote endpoint needs `THANZI_LLM_ALLOW_REMOTE=1` **and** https, and should happen only after a data protection review. A single-word name could in theory resolve to a public host through DNS search domains; run the model on a network that has no route out (compose example).
- **No credentials in URLs**, no query strings, no redirects followed, proxy environment variables ignored (a stray `HTTPS_PROXY` cannot carry private traffic out).
- **Nothing sensitive in logs or errors.** Logs hold provider, model, latency, token counts and error codes. Prompts, replies, URLs and server error text are never logged or copied into an exception. Tests check this.
- **Replies are size-capped** while they are read, and parsed as JSON objects only.
- **Gateway key** protects both routes. The generate route is not for patient records: the prompt limit is small, the response says so, and the standing rule applies (synthetic data first, no identifiable patient data without authorisation). The client cannot tell whether text is identifiable, so keeping records out is a rule for callers, not a filter (I43).
- **Tests use synthetic text only** (`SYN-0001` style markers) and a fake loopback server. No test calls an external API.

## Low-resource guidance (D132)
- Start with a 0.5B to 1.7B model at 4-bit quantisation. A 1.5B model needs roughly 1 to 2 GB of RAM plus context; check on the real machine.
- Keep `MAX_CONCURRENCY=1`. Two generations at once on a small CPU are slower than two in turn and may run out of memory (an Ollama 500 is not retried for that reason).
- Keep context (2048) and `max_tokens` (256) small. These are the biggest levers on speed and memory.
- `KEEP_ALIVE=5m` avoids reloading the model for every call. Use `0` when RAM is needed for something else.
- The first request after a load is slow (model load). The 60 s default deadline is for a small model on a modest CPU; raise it for slower hardware.
- Qwen3-style models think out loud by default. Set `THANZI_LLM_THINK=false` (Ollama) to save tokens; any `<think>` text that still arrives is removed.

## Models
No weights are in this repository. Model tags change, and model licences differ between sizes of one family (as far as I know the Qwen2.5 3B model is under a different licence from the 0.5B and 1.5B models). Before any deployment, read the model card, and record source, version, date and licence in `docs/references/register.md` (R16 and R17 are placeholders, I44).

## Setup examples
Ollama on the same machine:
```
ollama pull qwen2.5:1.5b
THANZI_LLM_ENABLED=1 THANZI_LLM_MODEL=qwen2.5:1.5b THANZI_GATEWAY_KEY=<16+ characters> \
  uvicorn --factory thanzi_screen.api.app:create_app_from_env
curl -H "X-Gateway-Key: <key>" http://127.0.0.1:8080/v1/llm/health
```
(`pip install -c constraints.txt -e ".[api,llm]"` first.) llama.cpp: start `llama-server` with a Qwen GGUF file and `-c 2048 --parallel 1`, then set `THANZI_LLM_PROVIDER=llamacpp` and the endpoint. Containers: `deploy/docker-compose.llm.example.yml`, `deploy/Dockerfile.llm`, `deploy/llm.env.example`.

## Tests
`tests/llm/` (config and privacy policy, providers against `httpx.MockTransport`, client limits and retries, real loopback servers, isolation, packaging) and `tests/api/test_llm_routes.py` (routes, error mapping, shutdown, log privacy, screening unchanged with a dead model server). Without httpx, `tests/llm/test_providers.py` and `test_network.py` skip (they fail in CI, where `THANZI_REQUIRE_API_TESTS=1`).

## Not done (see I45 to I47)
No streaming, no circuit breaker, no filtering of model output, no real-server run and no UniPod measurement. Model text must not be shown to health workers without clinician review.
