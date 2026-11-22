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
3. **Rate Limiting**: Protects public auth, upload, verification, and admin endpoints. AI work is asynchronous, so long LLM/OCR jobs do not hold public connections open.
4. **Edge CORS**: Enforces browser security policies before requests reach `core-api`.
5. **Network Isolation**: `ai-service`, `notification-service`, Redis, and Postgres sit on an internal Docker network. Only Kong and `core-api` are edge-facing.
