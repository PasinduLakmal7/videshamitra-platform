# VideshaMitra — AI Migration Safety Companion

> **InnovaX 1.0 | Team QuadNova | University of Moratuwa**

VideshaMitra is a trilingual (Sinhala, Tamil, English), agentic AI migration-safety companion designed to protect Sri Lankan workers before, during, and after overseas employment.

---

## 🏛️ Project Architecture

```
web/
├── admin-frontend/     # React + Vite + TS caseworker/admin interface
├── web-backend/        # FastAPI + LangGraph hierarchical multi-agent backend
├── web-frontend/       # React + Vite + TS worker application
├── supabase/           # PostgreSQL migrations, schema, pg_trgm & RLS policies
├── docs/               # Technical documentation & specifications
├── infra/              # Deployment & containerization configurations
└── .github/            # CI/CD pipelines
```

---



---

## 🤖 Multi-Agent Workflow (LangGraph)
- **LangGraph Supervisor**: Orchestrates intents and controls state persistence.
- **Document & Contract Agent**: Multi-page OCR, clause analysis, and deduction checks.
- **Recruitment Verification Agent**: SLBFE register lookup, license validation vs. job approval, fuzzy name matching (`pg_trgm`).
- **Migration Guardian Agent**: Consent-based scheduled follow-ups (Day 7, 30, 90) and autonomous Agency Watchdog.
- **Case Support Agent**: Evidence organisation, complaint drafting, and human escalation.
