# Shared contracts

Versioned event and internal API contracts shared by `core-api`, `ai-service`
and `notification-service`.

## Contents

- `schemas/envelope.schema.json` — the common event envelope.
- `schemas/verification.requested.v1.schema.json`
- `schemas/verification.completed.v1.schema.json`
- `schemas/verification.failed.v1.schema.json`
- `schemas/notification.requested.v1.schema.json`
- `schemas/index.json` — machine-readable index.

The Pydantic models in `services/core-api/app/events/schemas.py` are the
canonical source. Generate the schemas with:

```bash
cd services/core-api
python scripts/export_contracts.py
```

Generate TypeScript types from the public OpenAPI contract:

```bash
# Admin portal (already generated)
cd admin-frontend
npm run generate:api

# Worker web (Person 3)
cd web-frontend
npx openapi-typescript ../docs/api/openapi.json -o src/types/api.generated.ts
```

CI runs `python scripts/export_contracts.py --check` and
`python scripts/export_openapi.py --check`, and regenerates the admin types to
fail if they are stale.

## Versioning policy

1. Event names are immutable. On the stream `event_type` has **no** version
   suffix (`verification.completed`), and `version` is the integer `1`. The
   `.v1` suffix appears only in schema file names and docs. A suffixed
   `event_type` is dropped by core as unknown.
2. Additive fields are allowed within a version only when consumers can ignore
   them. `core-api` currently rejects unknown envelope and result fields, so
   update the core models first. New required fields or changed semantics
   require a new version.
3. Breaking changes require a new event type (`*.v2`), a dual-publish window,
   and an explicit handoff between producers and consumers.
4. Never reuse an event type or field name with different meaning.
5. Every event carries `event_id` (UUID), `occurred_at` (UTC), `producer`,
   `trace_id`, and `version`.
6. Consumers must dedupe on `event_id` and tolerate unknown event types.

## Ownership

- `core-api` produces `verification.requested.v1` and
  `notification.requested.v1`.
- `ai-service` produces `verification.completed.v1` and
  `verification.failed.v1`.
- `notification-service` may produce `notification.delivery.updated.v1`.

Changes to these contracts require agreement from both sides before merge.
