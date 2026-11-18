# Kong API Gateway — VideshaMitra

Kong Gateway OSS runs in **DB-less mode** using declarative configuration (`kong.yml`).

## Features:
1. **Single Entry Point**: Frontends (Web, Admin, Mobile) send traffic to Kong on port `8000`.
2. **Rate Limiting**: Protects expensive LangGraph multi-agent and LLM verification endpoints (120 req/min).
3. **Edge CORS**: Enforces browser security policies before requests reach the FastAPI service.
4. **Proxy Routing**: Routes `/api/v1/*` and `/health` to internal `http://web-backend:8000`.
