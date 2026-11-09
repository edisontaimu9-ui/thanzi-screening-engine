# Configuration

All configuration is through environment variables. An invalid value stops start-up and names the variable, never its
content.

## Service

| Variable | Required | Default | Description |
|---|---|---|---|
| `THANZI_GATEWAY_KEY` | yes | none | Shared secret the gateway sends as `X-Gateway-Key`. At least 16 characters (use 48 hex). The service refuses to start without it. |
| `THANZI_AUDIT_KEY` | no | unset | Second secret for `?view=audit`, sent as `X-Audit-Key` together with the gateway key. At least 16 characters and different from the gateway key. If unset the audit view is off (403). |
| `THANZI_MODELS_DIR` | no | `models/` in the repository (`/app/models` in the image) | Directory with the trained model files. Missing or mismatched files start the service in degraded mode. |
| `THANZI_DEEP_ENABLED` | no | on | Set `0`, `false`, `no` or `off` to disable the neural-network recording-error flag. Screening and the logistic flag are unchanged. |
| `PORT` | no | `8080` | Listening port in the container image. |
| `THANZI_DEV_MODE` | no | off | `1` exposes the documentation routes and allows a missing key. **Local development only. Never set in production.** |
| `THANZI_LLM_ENABLED` | no | off | Must be exactly `1` to mount the optional language-model routes. |

Generate keys with `openssl rand -hex 24`. Keys are read from environment variables only; there is no file-based
secret support. Anyone who can run `docker inspect` on the host can read them, so restrict host access and supply
them from a secret store.

## Optional language-model client

Read only when `THANZI_LLM_ENABLED=1`. All are optional. A fully annotated example is in
[`deploy/llm.env.example`](../deploy/llm.env.example).

| Variable | Default | Description |
|---|---|---|
| `THANZI_LLM_PROVIDER` | `ollama` | `ollama`, `llamacpp`, `openai_compat` or `mock` |
| `THANZI_LLM_ENDPOINT` | `http://127.0.0.1:11434` | Base URL of the model server |
| `THANZI_LLM_MODEL` | `qwen2.5:1.5b` | Model tag (a label only for llama.cpp) |
| `THANZI_LLM_API_KEY` | none | Bearer token for servers that need one. Never logged |
| `THANZI_LLM_CONNECT_TIMEOUT_S` | 3 | Connect timeout |
| `THANZI_LLM_TIMEOUT_S` | 60 | Whole-generation deadline |
| `THANZI_LLM_HEALTH_TIMEOUT_S` | 2 | Health check timeout |
| `THANZI_LLM_QUEUE_TIMEOUT_S` | 5 | Wait for a free slot before `llm_busy` |
| `THANZI_LLM_MAX_CONCURRENCY` | 1 | Parallel generations (1 to 8) |
| `THANZI_LLM_MAX_RETRIES` | 1 | Retries for transient errors only |
| `THANZI_LLM_RETRY_BACKOFF_S` | 0.5 | Exponential backoff base |
| `THANZI_LLM_MAX_PROMPT_CHARS` | 8000 | Input cap |
| `THANZI_LLM_MAX_RESPONSE_BYTES` | 1048576 | Reply cap |
| `THANZI_LLM_KEEP_ALIVE` | `5m` | Ollama: how long the model stays loaded |
| `THANZI_LLM_THINK` | not sent | Ollama: `false` disables visible reasoning |
| `THANZI_LLM_STRIP_REASONING` | true | Remove `<think>` blocks from replies |
| `THANZI_LLM_MAX_TOKENS` | 256 | Generation limit |
| `THANZI_LLM_TEMPERATURE` | 0.2 | Sampling temperature |
| `THANZI_LLM_TOP_P`, `_TOP_K`, `_SEED` | unset | Sampling controls |
| `THANZI_LLM_CONTEXT_TOKENS` | 2048 | Ollama context size |
| `THANZI_LLM_ALLOW_REMOTE` | 0 | Allow a non-local endpoint (https only). Requires a data protection review |

## Build-time settings

| Item | Value |
|---|---|
| Python | 3.11 or 3.12 |
| Install | `pip install -c constraints.txt -e ".[dev,api]"` (add `llm` for the language-model client) |
| Pinned versions | `constraints.txt` pins every dependency. Regenerate with `scripts/refresh_constraints.py` |
| Image build argument | `VERSION`, recorded in the image label |
