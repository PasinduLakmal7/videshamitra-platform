-- 004_llm_usage.sql
-- Per-call LLM usage ledger. The daily token budget sums this table; chat calls have no run.

create table if not exists ai.llm_usage (
    id bigint generated always as identity primary key,
    created_at timestamptz not null default now(),
    model text not null,
    purpose text not null,
    run_id uuid references ai.analysis_runs (id) on delete set null,
    tokens_in integer not null check (tokens_in >= 0),
    tokens_out integer not null check (tokens_out >= 0),
    cost_usd numeric(12, 6) not null default 0
);

create index if not exists llm_usage_created_idx on ai.llm_usage (created_at);
