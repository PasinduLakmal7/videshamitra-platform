# VideshaMitra — AI Migration Safety Companion

> **InnovaX 1.0 | Team QuadNova | University of Moratuwa**

VideshaMitra is a trilingual (Sinhala, Tamil, English), agentic AI migration-safety companion designed to protect Sri Lankan workers before, during, and after overseas employment.

---

## 📱 Platforms

| Platform | Primary users | Stack |
|---|---|---|
| Worker mobile app (separate repository) | **Migrant workers ("normal users")** — primary channel | Flutter (Dart) + FCM |
| `web-frontend/` | Migrant workers (browser access) | React + Vite + TypeScript |
| `admin-frontend/` | SLBFE caseworkers & admins | React + Vite + TypeScript |
| `services/core-api/` | All clients — public API | FastAPI + asyncpg + Redis |
| `services/ai-service/` (planned) | Core API — internal | FastAPI + LangGraph + Gemini |
| `services/notification-service/` | Core API — internal | FastAPI + FCM/WhatsApp |

The worker mobile app is the primary product for normal users. It is Android-first and built for low-connectivity environments, with:

- Phone-first onboarding in Sinhala, Tamil, or English
- Camera-based contract and job-offer capture
- AI chat with voice input/output
- Push-notified Day 7 / 30 / 90 safety check-ins
- Offline access to guidance, verification history, and complaint drafts
- One-tap escalation to a human caseworker

The mobile app is worker-only; caseworker and admin workflows stay in `admin-frontend/`.

---

## 🏛️ Project Architecture

```
videshamitra-platform/
├── services/
│   ├── core-api/            # Public API, transactional core, admin APIs
│   ├── ai-service/          # (planned) LangGraph, OCR, LLM, speech, traces
│   └── notification-service/ # Device tokens, preferences, FCM/WhatsApp delivery
├── packages/contracts/      # Versioned event + internal API contracts
├── admin-frontend/          # React + Vite + TS caseworker/admin interface
├── web-frontend/            # React + Vite + TS worker web application
├── supabase/                # Local Supabase config, Auth/Storage bootstrap
├── docs/                    # Technical documentation & specifications
├── infra/                   # Kong, Docker, deployment configuration
└── .github/                 # CI/CD pipelines
```

Only `services/core-api/` is exposed through Kong. `ai-service` and `notification-service` are internal services. All clients call the same `/api/v1` public API.

> **Migration note:** `web-backend/` has moved to `services/core-api/`; the
> public API, migrations, workers, contracts, Compose and admin portal are in
> place. See [`docs/progress.md`](docs/progress.md) for verified scope and
> remaining work.

The worker mobile app is maintained in a **separate repository**. This repository owns the API contract, database, and product documentation; mobile source code is not maintained here.

### Quick start (core platform)

```bash
supabase start
psql "postgresql://postgres:postgres@localhost:54322/postgres" -f supabase/bootstrap.sql
cd services/core-api
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp ../../.env.example ../../.env                  # fill in Supabase keys + INTERNAL_JWT_SECRET (openssl rand -hex 32)
.venv/bin/python -m app.db.migrate
.venv/bin/python scripts/seed_demo_data.py
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Run the background workers with `.venv/bin/python -m app.workers.runner`, or
bring up Kong + core + worker + Redis with `docker compose up --build`
(public edge: `http://localhost:8000`). Admin portal: `admin-frontend/`
(`npm run dev`, port 5174). See [`services/core-api/README.md`](services/core-api/README.md).

Notification service: apply its migrations with an admin DSN, start
`uvicorn app.main:app --port 8020` and `python -m app.worker`, or use the
`notification-service` / `notification-worker` Compose services. See
[`services/notification-service/README.md`](services/notification-service/README.md).

---

## 🔗 Related Repositories

| Repository | Contents |
|---|---|
| **videshamitra-platform** (this repo) | Three services (`core-api` and `notification-service` implemented; `ai-service` in progress), worker web portal, admin portal, database, infrastructure, documentation |
| **Worker mobile app** (separate repo) | Flutter app for migrant workers (Android first, then iOS); consumes the same `/api/v1` API |

---

## 📲 Worker Mobile App

The app source lives in a separate repository; this section documents scope and shared contracts.

- **Framework:** Flutter (Dart), `go_router` navigation
- **State/data:** Riverpod + `dio` against the core `/api/v1` API
- **Auth:** tokens from `core-api` `/auth/*`, stored in `flutter_secure_storage`
- **Notifications:** Firebase Cloud Messaging (`firebase_messaging`; iOS through FCM's APNs bridge)
- **Offline:** cached guidance, verification history, and queued submissions
- **Media:** camera capture, document picker, voice recording/playback
- **Localization:** Sinhala / Tamil / English (`flutter_localizations` + ARB files)
- **Distribution:** Play Store first, then App Store

Full specification: [`docs/mobile/overview.md`](docs/mobile/overview.md)

---

## 🤖 Multi-Agent Workflow (LangGraph)

- **LangGraph Supervisor**: Orchestrates intents and controls state persistence.
- **Document & Contract Agent**: Multi-page OCR, clause analysis, and deduction checks.
- **Recruitment Verification Agent**: SLBFE register lookup, license validation vs. job approval, using core's fuzzy `pg_trgm` agency search.
- **Migration Guardian Agent**: Consent-aware guidance and risk triage; Day 7/30/90 scheduling and the Agency Watchdog run as `core-api` workers.
- **Case Support Agent**: Evidence organisation, complaint drafting, and human escalation.

The agent engine runs in `services/ai-service/` (planned, Person 2) on Gemini behind a provider-neutral adapter. Verification jobs arrive asynchronously over Redis Streams; chat and speech are proxied through `core-api`. Caseworkers review agent outputs and escalations in the admin portal. The internal contract is in [`docs/ai-agents/multi-agent-spec.md`](docs/ai-agents/multi-agent-spec.md).

---

## 📚 Documentation

- [System architecture](docs/architecture/system-architecture.md)
- [Architecture overview](docs/architecture/overview.md)
- [Microservice architecture](docs/architecture/microservices.md)
- [Core API implementation plan](docs/core-api-plan.md)
- [API endpoints](docs/api/endpoints.md)
- [Database schema](docs/database/schema.md)
- [Multi-agent specification](docs/ai-agents/multi-agent-spec.md)
- [Worker mobile app](docs/mobile/overview.md)
- [Project progress](docs/progress.md)
- [Agent rules](agent-rules.md)

---

## 🤖 For AI Agents

Read [`agent-rules.md`](agent-rules.md) and [`docs/progress.md`](docs/progress.md) before making changes.

Every run must update `docs/progress.md` with the relevant scope, changes, verification, decisions, blockers, and next action. Only update sections affected by the run; do not bulk-rewrite unrelated statuses.