# AI Service — Multi-Agent Specification and Contract

**Owner:** Person 2 · **Service:** `services/ai-service/` (planned, internal only) · **LLM:** Gemini behind a provider-neutral adapter

`ai-service` runs the LangGraph agents, document extraction, chat, speech and AI traces. It never touches the `core` schema. It talks to `core-api` only through the internal HTTP endpoints and Redis streams defined below. Section 4 records what core implements **today**; the change requests in section 9 cover what the AI still needs from core.

---

## 1. Agents

| Agent | Responsibility |
|---|---|
| **Supervisor** | Intent detection, routing, 3-tier triage, session lock on Tier 3 / duress |
| **Document & Contract Analysis** | Multi-page stitching, extraction (employer, salary, fees, visa type, destination, agency, contacts), clause/deduction checks, Singlish/Tanglish normalisation |
| **Recruitment Verification** | SLBFE register status (licence vs. job approval), near-miss name warnings, red-flag rules, scam fingerprints |
| **Migration Guardian** | Milestone-aware guidance; decides check-in wording and risk. Scheduling, delivery and the agency watchdog run as `core-api` workers |
| **Case Support** | Evidence bundling, LankaKonect-ready complaint drafts (user approves), human escalation |

### Tools

| Tool | Backed by |
|---|---|
| `lookup_agency` | core internal agency search (CR-2); `pg_trgm` lives in core |
| `analyse_document` | Gemini multimodal on bytes from `/internal/v1/documents/{id}/content` |
| `compare_contract_terms` | `ai.fee_rules` / `ai.wage_floors` / `ai.red_flag_rules` (configurable tables, not code) |
| `match_recruitment_entities` | `ai.scam_fingerprints` (HMAC-hashed phones, bank accounts, WhatsApp numbers) |
| `watch_agency_status` | core license history (`/internal/v1/agencies/{id}/license-history`) |
| `schedule_checkin` | core journeys/check-ins (scheduling stays in core) |
| `prepare_complaint` | core complaint draft (CR-4) |

### Triage tiers

| Tier | Meaning | Action |
|---|---|---|
| 1 | Information request | Autonomous answer with citations |
| 2 | Suspected fraud | Verdict + complaint draft offer; caseworker visible |
| 3 | Physical distress / trafficking / duress code phrase | Lock the session, stop autonomous flow, escalate to a human (CR-3) |

---

## 2. Guardrails (non-negotiable)

- **PII redaction** before every LLM call and every log line: NIC (old `#########V/X` and new 12-digit), passport numbers, `+94`/local phone numbers, emails, bank account numbers.
- **Untrusted input:** document text, OCR output and user messages are data, never instructions. Wrap them in delimited blocks and never let them change tools, roles or policies (prompt-injection defence).
- **Structured output:** every LLM response is validated against a Pydantic schema. Invalid output is retried once, then the run fails safely.
- **Source-grounded verdicts:** every finding cites a document page, an SLBFE record with its list date, or a rules-table row. A finding without a source is dropped. With no grounded findings the result is "unable to verify" (CR-1), never "safe".
- **Never says an agency is legal.** It reports official-list status with the list date. Every verdict includes the SLBFE 1989 hotline and an "independent AI assistant, not SLBFE" disclaimer.
- **No profiling:** never asks for ethnicity, religion or caste.
- **Data minimisation:** only IDs and redacted text leave the service. Traces exposed to staff contain no prompts, secrets or raw PII.

---

## 3. Data (`ai` schema, planned)

`analysis_runs`, `agent_traces`, `document_extractions`, `chat_sessions`, `chat_messages` (30-day retention by default), `checkpoints` (LangGraph Postgres saver), `fee_rules`, `wage_floors`, `red_flag_rules`, `scam_fingerprints`, `event_dedupe`. A least-privilege `ai_service_role` has grants on `ai` only.

---

## 4. Contract with core-api (as implemented today)

### 4.1 Internal auth

- **core → ai-service:** HS256 JWT signed with `INTERNAL_JWT_SECRET`; claims `iss=core-api`, `aud=ai-service`, `sub=core-api`, `iat`, `exp` (≤ 300 s). Headers `X-Request-ID`, `X-Trace-ID`. ai-service must verify signature, audience and issuer on every route except health.
- **ai-service → core:** same secret; claims `iss=ai-service`, `aud=core-api`, `sub=ai-service`, `iat`, `exp`. Lifetime over 300 s is rejected (`service_token_lifetime`), and `iat` is required. Send `X-Trace-ID`.
- Core's errors: 401 `service_token_missing|invalid|expired|lifetime`, 403 `service_token_audience|issuer`.

### 4.2 Endpoints ai-service must serve

Base URL `AI_SERVICE_URL` (Compose: `http://ai-service:8010`, internal network only, no published port).

| Method + path | Request from core | Notes |
|---|---|---|
| `GET /internal/v1/health` | 3 s timeout | Any status < 500 is healthy; shown in core `/ready` |
| `POST /internal/v1/chat/sessions` | `{user_id, title?, language?, context: {}}` | Core wraps the JSON in its `{data, meta}` envelope |
| `GET /internal/v1/chat/sessions?user_id=` | query only | List the worker's sessions |
| `GET /internal/v1/chat/sessions/{id}?user_id=` | `id` is a UUID | **Ownership check is yours:** return 404 if the session is not that user's. Core calls this before every message |
| `POST /internal/v1/chat/sessions/{id}/messages` | `Accept: text/event-stream`; `{user_id, content (1–8000), attachments: [uuid], language?}` | No timeout. Core has already checked that attachments are the user's own, non-deleted documents. **Always answer 200** and report failures as an SSE `error` event (a non-2xx breaks core's stream proxy) |
| `POST /internal/v1/speech/transcribe` | multipart `file` (webm/ogg/mpeg/mp4/wav, ≤ 10 MB) + optional `language` | 60 s timeout; return JSON `{text, language, confidence?}` |
| `POST /internal/v1/speech/synthesize` | `{text (≤ 5000), language, voice, format: mp3\|wav\|ogg}` (nulls sent explicitly) | 60 s timeout; raw audio with the right `Content-Type` |
| `GET /internal/v1/analyses/{verification_id}` | staff-only on the core side | Must return a **JSON object** (not a list): steps, tools, findings, citations, timings, model, token usage. No prompts or PII |
| `POST /internal/v1/webhooks/whatsapp` | raw Meta payload; header `X-Provider-Message-ID` | 30 s timeout. **Ack 2xx immediately** and process asynchronously; any error is returned to Meta, which retries |

**SSE events** (`event:` names): `token` `{text}`, `tool_start` `{tool}`, `tool_result` `{tool, summary}`, `citation` `{source, document_id?, page?, list_date?}`, `done` `{message_id, triage_tier}`, `error` `{code, message}`.

Core maps upstream errors: 404 → 404, 429 → rate limited, other 4xx → `upstream_rejected`, 5xx/network → 502.

### 4.3 Core endpoints ai-service can call

All need the service JWT with `iss=ai-service`. Every call is audited.

- `GET /internal/v1/documents/{id}/content` — raw bytes (`application/pdf`, `image/jpeg`, `image/png`), `Cache-Control: no-store`; 404 missing; 403 over `MAX_UPLOAD_MB`.
- `GET /internal/v1/agencies/{id}/license-history` — `{agency, licenses: [...]}`.
- `GET /internal/v1/verifications/{id}` — `{verification, documents: [... oldest first]}`.
- `POST /internal/v1/audit-events` — `{action (≤ 100), entity_type?, entity_id?, metadata: {}}`.

### 4.4 Events (Redis Streams)

- Each stream entry has one field `event` holding compact JSON of the envelope `{event_id, event_type, version, occurred_at, producer, trace_id, data}`. **No extra envelope fields.**
- `event_type` has **no** `.v1` suffix (`verification.completed`); `version` is `1`. A suffixed type is silently dropped by core.
- **Consume** `vm:ai:requests` with consumer group `ai-service`. Core does not create the group; create it with `XGROUP CREATE ... MKSTREAM`. Dedupe on `event_id` in `ai.event_dedupe`. Expect the **same `verification_id` more than once** (retries, staff reprocess and stale recovery each publish a new `event_id`).
- `verification.requested` data: `verification_id`, `user_id`, `locale` (`en|si|ta`), `agency {id?, registration_no?, name?, license_no?, license_status, license_expires_on?}` or null (with no match, `name` is the raw user input and `id` is null), `job {title?, employer_name?, destination_country?, offered_salary?, currency?}`, `documents [{document_id, type, mime_type, page_count?}]`.
- **Publish** to `vm:ai:results` (core group `core-api`) and reuse the request's `trace_id`:
  - `verification.completed` data (no extra keys): `verification_id`, `status` (`verified|suspicious|fraudulent`), `risk_level` (`low|medium|high|critical`), `risk_score` (0–100 or null), `findings [{code, message, source?, ...}]`, `evidence [{document_id?, page?, quote?, ...}]`, `engine_version?`, `analysis_run_id?`.
  - `verification.failed` data: `verification_id`, `error_code`, `message` (≤ 2000), `retryable`. Core does **not** auto-retry on `retryable`.
- Results apply only while the verification is `pending`/`processing`; late results are recorded and ignored. Invalid payloads are retried and land in `vm:ai:results:dlq` after 5 attempts.
- Core marks a verification `failed` (`analysis_timeout`) if it stays `pending`/`processing` past `STALE_PROCESSING_MINUTES` after `MAX_VERIFICATION_RETRIES` re-queues. Aim for < 15 s per text verdict.
- A completed result creates a worker notification. It does **not** open a case for high-risk verdicts yet (CR-8).

---

## 5. Channels

- Worker mobile app (Flutter, primary), worker web portal, WhatsApp (webhook through core).
- Channel adapters normalise text, voice and documents, and format replies per channel. In-conversation WhatsApp replies are sent by `ai-service` through the WhatsApp Cloud API; proactive alerts go through `notification-service`.
- The admin portal reads traces through core's `GET /admin/verifications/{id}/trace`; it never chats with agents.

## 6. Configuration (ai-service env, planned)

`DATABASE_URL` (ai role), `REDIS_URL`, `INTERNAL_JWT_SECRET`, `CORE_API_URL`, `GEMINI_API_KEY`, `GEMINI_MODEL_FAST`, `GEMINI_MODEL_PRO`, `LLM_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `FINGERPRINT_PEPPER`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `CHAT_RETENTION_DAYS`, `ENVIRONMENT`.

## 7. Evaluation targets (from the proposal)

| Metric | Target |
|---|---|
| Agency match accuracy on 50 misspelt names | ≥ 95% |
| Red-flag recall on labelled real/fake ads | ≥ 90% |
| Distress messages routed to a human | 100% |
| Native-speaker rating of si/ta answers (30 prompts) | ≥ 4 / 5 |
| Time to first verdict (text) | < 15 s |

## 8. Out of scope for ai-service

Public routes, auth of end users, check-in scheduling, notification delivery, and direct reads of `core` tables.

## 9. Core change requests (owned by Person 1, specified by Person 2)

| ID | Need | Blocks |
|---|---|---|
| CR-1 | `unable_to_verify` outcome (enum + `verification.completed` status) | Honest "Unable to Verify" verdicts |
| CR-2 | `GET /internal/v1/agencies/search?q=&license_no=` (trigram, list date) | `lookup_agency` |
| CR-3 | `POST /internal/v1/cases/escalations` `{user_id, triage_tier, summary, reasons, verification_id?, chat_session_id?}` (idempotent) | Tier 3 / duress escalation |
| CR-4 | `POST /internal/v1/complaints/drafts` `{user_id, draft_text, case_file, sha256}` | Case Support drafts |
| CR-5 | `GET /internal/v1/users/by-phone?phone=` → `{user_id, locale, consents}` | WhatsApp conversations |
| CR-6 | Data rights: `DELETE` / `MY DATA` (public + internal) | PDPA commands |
| CR-7 | Family contact + consent type | Silent-alarm check-ins |
| CR-8 | Open a tier-2 case when a verdict is `high`/`critical` | Caseworker queue from AI verdicts |
| CR-9 | Localised (si/ta) notification text | Trilingual alerts |

Until a CR lands, ai-service uses the stub described in the Person 2 roadmap and records the blocker in `docs/progress.md`.
