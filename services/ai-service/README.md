# ai-service

Internal AI engine for VideshaMitra: agents, guardrails, document extraction and the
verification pipeline. It is reachable only from `core-api` on the internal network
(port 8010, no published port). The contract is
[`docs/ai-agents/multi-agent-spec.md`](../../docs/ai-agents/multi-agent-spec.md).

## Run

```bash
cd services/ai-service
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8010 --reload
curl -s localhost:8010/internal/v1/health
```

Settings load from the root `.env`, then `services/ai-service/.env`, which overrides it.

## Test

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/pytest -q
```

Tests use no network. HTTP to core is mocked with respx.

## Auth

Every `/internal/v1/*` route except `/internal/v1/health` requires a core service JWT:
HS256 with `INTERNAL_JWT_SECRET`, `iss=core-api`, `aud=ai-service`, and `sub`, `iat`
and `exp` present. The lifetime must be at most 300 s. Calls to core use a fresh
60 s token with `iss=ai-service` and `aud=core-api`.

## Environment

| Variable | Notes |
|---|---|
| `ENVIRONMENT` | Defaults to `production`; use `development` or `test` locally |
| `INTERNAL_JWT_SECRET` | Shared with core; at least 32 characters |
| `CORE_API_URL` | `http://localhost:8000` on the host, `http://core-api:8000` in Compose |
| `REDIS_URL` | Same Redis as core |
| `DATABASE_URL` | `ai_service_role` DSN (from Phase 2); put it in `services/ai-service/.env` |
| `GEMINI_API_KEY` | Required outside development/test. The free tier may train on prompts, so send only synthetic or redacted data |
| `GEMINI_MODEL_FAST`, `GEMINI_MODEL_PRO` | Model IDs |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_DAILY_TOKEN_BUDGET` | Cost control |
| `FINGERPRINT_PEPPER` | At least 32 characters; required outside development/test |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | In-conversation WhatsApp replies |
| `CHAT_RETENTION_DAYS` | Default 30 |

Secrets are `SecretStr` and never logged. Every log line passes through PII redaction.
