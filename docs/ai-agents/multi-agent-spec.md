# LangGraph Multi-Agent Architecture

The agent engine runs inside `services/ai-service/`, a separate internal service. It does not access the `core` database directly.

## Agents

1. **Supervisor Agent**: Understands intent, routes tasks, assesses urgency (Tier 1/2/3).
2. **Document & Contract Analysis Agent**: Multi-page stitching, salary deduction & clause analysis.
3. **Recruitment Verification Agent**: SLBFE register cross-referencing, license vs job approval.
4. **Migration Guardian Agent**: Consent-aware safety guidance and risk triage. Scheduling, check-in delivery, and the Agency Watchdog run as `core-api` workers.
5. **Case Support Agent**: Case evidence organization and human escalation dispatch.

## Deployment and boundaries

- **Owner:** Person 2 (`services/ai-service/`).
- **Database:** owns the `ai` schema — analysis runs, agent traces, OCR text, chat sessions/messages, LangGraph checkpoints.
- **Long-running work:** consumes `verification.requested.v1` from Redis stream `vm:ai:requests`; publishes `verification.completed.v1` or `verification.failed.v1` to `vm:ai:results`.
- **Document access:** fetches bytes from `core-api /internal/v1/documents/{id}/content` using a service JWT.
- **No direct access** to `core` tables, `core.users`, or `core.documents`.
- **Chat and speech:** internal endpoints called only by `core-api`; clients never reach `ai-service` directly.
- **Idempotency:** dedupes by `event_id`; retries are bounded and failures go to a dead-letter stream.

## Channels

- Worker mobile app (primary channel for normal users)
- Worker web portal
- WhatsApp webhook (via core-api)

Channel adapters normalize text, voice, and document input and format responses for the client. The admin portal consumes case summaries, AI traces, and escalations from `core-api` rather than chatting with agents directly.

## Admin trace

`core-api` exposes `GET /admin/verifications/{id}/trace`, which proxies the AI trace from `ai-service` after verifying the staff role. AI-service never returns prompts or secrets to the browser.
