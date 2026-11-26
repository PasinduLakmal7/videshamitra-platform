# notification-service

Internal delivery service for VideshaMitra. It owns device tokens, notification
preferences, delivery attempts and retries, and sends push through **Firebase
Cloud Messaging (FCM)**. WhatsApp template delivery is implemented behind a
feature flag. The service is reachable only from `core-api` on the internal
network (port `8020`, no published port, no Kong route).

The event and internal API contracts are frozen in
[`docs/architecture/microservices.md`](../../docs/architecture/microservices.md)
and [`packages/contracts`](../../packages/contracts). `core-api` owns the in-app
feed; this service never reads the `core` schema.

## Responsibilities

- Own the `notification` schema and `notification_service_role`.
- Register/unregister FCM tokens (multiple devices per user).
- Store per-user channel opt-in, quiet hours and timezone.
- Consume `notification.requested` events from `vm:notifications:requests` and
  dedupe by `event_id`.
- Send FCM push and record every attempt, retry transient failures with
  exponential backoff, and prune invalid tokens.
- Optionally send WhatsApp Cloud API template messages (`WHATSAPP_ENABLED=true`).
- Publish nothing by default; `notification.delivery.updated.v1` is deferred.

## Run

```bash
cd services/notification-service
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Create `services/notification-service/.env` (gitignored):

```dotenv
DATABASE_URL=postgresql://notification_service_role:<password>@localhost:54322/postgres
MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:54322/postgres
ENVIRONMENT=development
INTERNAL_JWT_SECRET=<same value as core-api, at least 32 chars>
PUSH_PROVIDER=stub
WHATSAPP_ENABLED=false
```

The root `.env` is loaded first, then this service-local file overrides it.

Set the role password once, out of band:

```bash
psql "$MIGRATION_DATABASE_URL" \
  -c "alter role notification_service_role with login password '<openssl rand -hex 24>'"
```

Create the schema and tables with an admin DSN:

```bash
.venv/bin/python -m app.db.migrate --dsn "$MIGRATION_DATABASE_URL"
.venv/bin/python -m app.db.migrate --status
```

API:

```bash
.venv/bin/uvicorn app.main:app --port 8020 --reload
curl -s localhost:8020/internal/v1/health
```

Worker (consumer + delivery retries):

```bash
.venv/bin/python -m app.worker
```

## Database

The runtime role has DML on `notification` only. It cannot create objects, read
`core`/`ai`, or read `notification.schema_migrations`. Migrations run with the
admin DSN and are checksum-locked; never edit an applied migration.

Tables:

- `device_tokens` — FCM registration tokens, platform, app version, last seen.
- `notification_preferences` — channel opt-in, quiet hours, timezone, locale.
- `deliveries` — one row per notification × channel × device, with content and
  scheduling fields.
- `delivery_attempts` — every provider call, HTTP status, provider id and error.
- `event_dedupe` — consumer idempotency by `(consumer, event_id)`.

## Internal API

Every `/internal/v1/*` business route requires a core service JWT
(`iss=core-api`, `aud=notification-service`, `iat` + `exp` ≤ 300 s). Health
routes are unauthenticated.

| Method | Path |
|---|---|
| `POST` | `/internal/v1/devices` |
| `DELETE` | `/internal/v1/devices/{token}?user_id=` |
| `GET` | `/internal/v1/preferences/{user_id}` |
| `PUT` | `/internal/v1/preferences/{user_id}` |
| `GET` | `/internal/v1/health` |
| `GET` | `/health`, `/ready` |

Responses are plain JSON; `core-api` wraps them in its own `{data, meta}`
envelope. The public `PATCH /api/v1/notifications/preferences` maps to this
service's partial `PUT`.

## Delivery behavior

- Requested channels: `push`, `whatsapp`, `email`, `sms`. `in_app` is ignored
  because `core-api` already wrote the feed row. `email`/`sms` are recorded as
  skipped/unsupported.
- Push fans out one delivery per active FCM token. If there are no tokens, a
  skipped `no_device` row is recorded.
- Quiet hours defer (not drop) push and WhatsApp deliveries. Default timezone is
  `Asia/Colombo`; start and end are HH:MM, overnight windows are supported, and
  `start == end` disables quiet hours.
- FCM `data` is string-only. Event `data` is stringified (nested values become
  compact JSON), and `type`, `notification_id` and `deep_link` are always
  included. Mobile-specific fields (sound, channel, category, rich media) are
  deliberately not set.
- Retries: 6 attempts, 30 s base backoff, 1 h cap, full jitter; `Retry-After` is
  respected. Permanent errors fail immediately; `UNREGISTERED` /
  `SENDER_ID_MISMATCH` deactivate the token.
- WhatsApp template delivery uses a single placeholder template
  (`WHATSAPP_TEMPLATE_NAME`, `WHATSAPP_TEMPLATE_LANGUAGE`) with title/body
  parameters. The notification event currently has no phone number, so the
  adapter needs a `phone` value in `data` (or a future contract addition) before
  WhatsApp can actually send.

## Providers

`PUSH_PROVIDER=stub` is the default for development/CI and never calls a
provider. `PUSH_PROVIDER=fcm` uses FCM HTTP v1 with a service-account OAuth2
token (`FCM_PROJECT_ID` plus `FCM_SERVICE_ACCOUNT_FILE` or
`FCM_SERVICE_ACCOUNT_JSON`). Real credentials are placeholders in `.env.example`.

WhatsApp is disabled by default. Enable with `WHATSAPP_ENABLED=true` and set
`WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_TEMPLATE_NAME`,
`WHATSAPP_TEMPLATE_LANGUAGE`.

No provider token is logged. Delivery content and phone numbers are not logged.

## Tests

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/pytest -q
```

Integration tests need a disposable Postgres:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/videshamitra_test \
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/videshamitra_test \
MIGRATION_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/videshamitra_test \
INTERNAL_JWT_SECRET=test-internal-secret-at-least-32-chars \
ENVIRONMENT=test \
.venv/bin/pytest -q tests/integration
```

## Known gaps / next steps

- Real FCM delivery cannot be verified until a Firebase project and service
  account are supplied.
- WhatsApp needs approved templates and a recipient source; the frozen
  `notification.requested` event does not include a phone number.
- Per-peer internal JWT secrets are a release gate (see
  `docs/architecture/system-architecture.md` §9.2); the service currently uses
  the shared `INTERNAL_JWT_SECRET`.
