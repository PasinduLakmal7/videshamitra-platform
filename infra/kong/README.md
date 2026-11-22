# Kong API Gateway — VideshaMitra

Kong Gateway OSS runs in **DB-less mode** using declarative configuration (`kong.yml`).

## Services

| Service | Route | Public |
|---|---|---|
| `core-api` | `/api/v1/*`, `/health` | **Yes** |
| `ai-service` | — | No (internal only) |
| `notification-service` | — | No (internal only) |

## Features

1. **Single Public Entry Point**: Clients (worker mobile app, worker web portal, admin portal) send traffic to Kong on port `8000`. Native mobile clients use the same routes; CORS applies only to browser clients.
2. **Only `core-api` Is Routed**: Kong proxies `/api/v1/*` and `/health` to `http://core-api:8000`. `ai-service` and `notification-service` are never exposed through Kong.
3. **Rate Limiting**: One global limit per client IP (600/min, 20,000/hour, `policy: local`). There are no per-route limits at the edge; `core-api` adds Redis-backed limits for OTP request/verify and login. AI work is asynchronous, so long LLM/OCR jobs do not hold public connections open.
4. **Edge CORS**: Enforces browser security policies before requests reach `core-api`.
5. **Network Isolation**: Redis (and later `ai-service` and `notification-service`) sit on the internal Docker network with no published ports. Only Kong publishes a host port. Postgres runs outside Compose through the Supabase CLI (host ports 54321/54322). `/internal/*`, `/ready`, `/docs` and `/openapi.json` are not routed by Kong.
