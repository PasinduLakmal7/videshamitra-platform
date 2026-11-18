# VideshaMitra Architecture Overview

VideshaMitra is a multilingual, agentic AI migration-safety companion designed to protect Sri Lankan workers before, during, and after migration.

## Systems:
1. `web-frontend`: Migrant worker portal (React + Vite + TypeScript)
2. `admin-frontend`: Caseworker and administration portal (React + Vite + TypeScript)
3. `web-backend`: REST API & LangGraph Multi-Agent Engine (FastAPI + LangGraph)
4. `supabase`: PostgreSQL with `pg_trgm`, auth, and checkpointer storage
