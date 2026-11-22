# core-api

Public API and transactional core for VideshaMitra.

- **Owner:** Person 1
- **Public entry point:** Kong → `core-api` (`/api/v1`, `/health`)
- **Plan:** [`docs/core-api-plan.md`](../../docs/core-api-plan.md)
- **Progress:** [`docs/progress.md`](../../docs/progress.md)

It owns `core` schema data (users, consents, agencies, verifications, document
metadata, journeys, check-ins, complaints/cases, in-app notifications, audit)
and orchestrates AI work asynchronously through Redis Streams. It never runs
LLM/OCR work and never stores device tokens or delivery state.

## Layout

```
app/
  api/v1/          public routes
  api/internal/    service-JWT routes for ai-service
  core/            config, security, errors, idempotency, logging
  db/              asyncpg pool, Redis, migration runner
  events/          envelope, schemas, outbox publisher, stream consumer
  integrations/    Supabase Auth/Storage, ai-service, notification-service, SLBFE
  models/          enums and domain identities
  repositories/    explicit SQL per aggregate
  schemas/         Pydantic request/response DTOs
  services/        business logic
  workers/         outbox relay, AI results, check-ins, agency monitor, cleanup
migrations/        core schema (001–011)
scripts/           OpenAPI, contracts, SLBFE import, demo seed
tests/             unit, contract, integration
```

## Local setup

Prerequisites: Python 3.11+, the Supabase CLI, Redis, and Docker (optional).

```bash
# 1. Local Supabase (Postgres/Auth/Storage)
supabase start

# 2. Bootstrap the service schema/role
psql "postgresql://postgres:postgres@localhost:54322/postgres" -f supabase/bootstrap.sql

# 3. Install and migrate
cd services/core-api
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp ../../.env.example ../../.env          # fill in local keys
.venv/bin/python -m app.db.migrate

# 4. Seed demo data (creates auth users through the Admin API when configured)
.venv/bin/python scripts/seed_demo_data.py

# 5. Run
.venv/bin/uvicorn app.main:app --reload --port 8000
.venv/bin/python -m app.workers.runner    # separate terminal
```

Kong is the public edge: `docker compose up --build` publishes
`http://localhost:8000`. Kong routes `/api/v1` and `/health`; `/ready` stays
internal.

### Environment

Start from [`.env.example`](../../.env.example). Required:
`DATABASE_URL` and `INTERNAL_JWT_SECRET`. Supabase Auth/Storage need
`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and either
`SUPABASE_JWT_SECRET` (local HS256) or JWKS settings. When core runs inside
Compose, set `SUPABASE_INTERNAL_URL=http://host.docker.internal:54321` for
server-to-server Auth/Storage calls while keeping `SUPABASE_URL` browser-facing
for signed URLs.

Local development can set `AUTH_DEV_OTP` to exercise the worker OTP flow without
an SMS provider. It only works for worker accounts, never staff, and the service
refuses to start if it is set outside `ENVIRONMENT=development|test`.
`ENVIRONMENT` defaults to `production`, so set it explicitly in `.env`.

## API conventions

- Base path `/api/v1`; bearer Supabase access token.
- Success: `{"data": ..., "meta": {"request_id": ...}}`; lists add `page`,
  `page_size`, `total`.
- Errors: `{"error": {"code", "message", "details"}, "meta": {"request_id"}}`.
- `X-Request-ID` / `X-Trace-ID` are echoed and propagated into events.
- `Idempotency-Key` is required on verification creation, document upload,
  check-in responses, and complaint creation.
- OpenAPI: `docs/api/openapi.json`; run `python scripts/export_openapi.py`.

## Events

Produced by core:

- `verification.requested.v1` → `vm:ai:requests`
- `notification.requested.v1` → `vm:notifications:requests`

Consumed by core:

- `verification.completed.v1` / `verification.failed.v1` from `vm:ai:results`
  (consumer group `core-api`, deduped by `event_id`).

Schemas live in [`packages/contracts/schemas`](../../packages/contracts/schemas)
and are generated with `python scripts/export_contracts.py`.

## Workers

`python -m app.workers.runner` runs:

- outbox relay (`FOR UPDATE SKIP LOCKED`, backoff, dead-letter)
- AI result consumer (`event_dedupe`)
- check-in scheduler and missed escalation
- agency license watchdog
- expired idempotency cleanup
- stale verification recovery

## Tests

```bash
.venv/bin/ruff check app scripts tests
.venv/bin/ruff format --check app scripts tests
.venv/bin/pytest -q
```

Migration integration tests run only when `TEST_DATABASE_URL` points at a
disposable database:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:55432/videshamitra_test \
  .venv/bin/pytest -q tests/integration
```

## Operations

- `/health` — liveness.
- `/ready` — Postgres, Redis, storage; internal clients are reported as
  degraded checks.
- Logs are JSON with `request_id`, `trace_id`, route, status, latency, and user
  ID. Document contents, full phone numbers, and complaint bodies are never
  logged.
- Migrations are append-only. Never edit an applied file; add the next number.
