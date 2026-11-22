# VideshaMitra Admin Portal

Caseworker and administrator console for the migration-safety platform.

- **Stack:** React 19 + Vite + TypeScript
- **API:** `services/core-api` (`/api/v1`), through Kong in production
- **Auth:** staff email/password through `POST /auth/login`; worker accounts are
  rejected by both the portal and the API role guards
- **Roles:** `caseworker` (cases/agencies), `admin` (also users/audit/imports)

## Pages

| Route | Page | Access |
|---|---|---|
| `/login` | Staff sign-in | public |
| `/` | Dashboard metrics + recent activity | staff |
| `/cases` | Case queue with status/tier/search filters | staff |
| `/cases/:id` | Case detail, evidence, documents, AI trace, notes, status/assignee, escalate | staff |
| `/agencies` | Agency search/license history, admin edit + SLBFE import | staff read, admin write |
| `/users` | User list, role/status changes | admin |
| `/audit` | Audit log filters + metadata detail | admin |

## Local setup

```bash
npm install
cp .env.example .env      # VITE_API_BASE_URL=http://localhost:8000/api/v1
npm run dev               # http://localhost:5174
```

If `VITE_API_BASE_URL` is unset the dev server proxies `/api` to
`http://localhost:8000`.

## Verification

```bash
npm run lint
npm run typecheck
npm run build
```

Generated API types come from the committed OpenAPI contract:

```bash
npm run generate:api      # writes src/types/api.generated.ts
```

Do not edit `src/types/api.generated.ts` by hand. Playwright E2E is still
pending; see [`docs/progress.md`](../docs/progress.md).
