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

## Database

ai-service owns the `ai` schema. At runtime it connects as `ai_service_role`, which has
DML on `ai` only: no CREATE, no access to `core`, and no access to the migration registry.
Migrations run with an admin DSN.

```bash
# apply migrations (admin DSN: --dsn, else MIGRATION_DATABASE_URL, else DATABASE_URL)
.venv/bin/python -m app.db.migrate --dsn postgresql://postgres:postgres@localhost:54322/postgres
.venv/bin/python -m app.db.migrate --status

# once per environment, out of band (never commit the password)
psql "$ADMIN_DSN" -c "alter role ai_service_role with login password '<openssl rand -hex 24>'"
```

`services/ai-service/.env` (gitignored):

```
DATABASE_URL=postgresql://ai_service_role:<password>@localhost:54322/postgres
MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
```

Integration tests need an admin DSN. On Supabase, also pass the runtime DSN, because
`postgres` there cannot `SET ROLE`:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres \
TEST_AI_DATABASE_URL="$DATABASE_URL" .venv/bin/pytest -q tests/integration
```

The rule tables (`fee_rules`, `wage_floors`, `red_flag_rules`) are seeded with
**demo data**, marked in each row's `source`. They are not official SLBFE figures.

## LLM

Every model call goes through `app.llm.usage.MeteredLLM`, wrapping a provider (`GeminiClient`;
`FakeLLM` in tests).

- **PII:** text parts pass through `guardrails.pii.redact` before they leave the service.
- **Models:** `ModelTier.FAST` is for classification and normalisation and uses low thinking;
  `ModelTier.PRO` is for multi-page contracts. Both default to `gemini-3.5-flash`, because the 2.5
  models are closed to new keys and the pro models need a paid key.
- **Failures:** each attempt has a hard timeout, and only 429, 5xx and transport errors are retried,
  with bounded backoff and jitter. Errors map to `llm_unavailable`, `llm_rejected` or
  `llm_invalid_output`, and provider messages are truncated and redacted.
- **Budget:** each call is logged in `ai.llm_usage`, and added to `ai.analysis_runs` when there is a
  run. Calls are refused with `budget_exceeded` once the daily total reaches
  `LLM_DAILY_TOKEN_BUDGET`, or with `llm_unavailable` if the usage ledger can't be read.

The SDK supports both `httpx` and `httpx2`, so `GeminiClient` passes in its own `httpx.AsyncClient`.
That keeps errors predictable and lets respx intercept every request: unit tests never reach the
network.

Manual smoke test against the real API, using a synthetic prompt (not run in CI):

```bash
ENVIRONMENT=development .venv/bin/python scripts/llm_smoke.py [--pro]
```

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
| `DATABASE_URL` | `ai_service_role` DSN; put it in `services/ai-service/.env` |
| `MIGRATION_DATABASE_URL` | Admin DSN used only by `app.db.migrate` |
| `DATABASE_MIN_POOL`, `DATABASE_MAX_POOL`, `DATABASE_COMMAND_TIMEOUT` | Pool sizing and query timeout |
| `GEMINI_API_KEY` | Required outside development/test. The free tier may train on prompts, so send only synthetic or redacted data |
| `GEMINI_MODEL_FAST`, `GEMINI_MODEL_PRO` | Model IDs |
| `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_DAILY_TOKEN_BUDGET` | Cost control |
| `FINGERPRINT_PEPPER` | At least 32 characters; required outside development/test |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` | In-conversation WhatsApp replies |
| `CHAT_RETENTION_DAYS` | Default 30 |

Secrets are `SecretStr` and never logged. Every log line passes through PII redaction.
