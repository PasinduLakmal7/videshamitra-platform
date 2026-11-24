-- 001_ai_foundation.sql
-- ai schema, least-privilege runtime role, analysis runs/traces, extractions, event dedupe.

create schema if not exists ai;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'ai_service_role') then
        create role ai_service_role nologin;
    end if;
end $$;

-- Runtime role: DML on schema ai only. No CREATE here and no grants on core.
revoke all on schema ai from public;
grant usage on schema ai to ai_service_role;
alter default privileges in schema ai
    grant select, insert, update, delete on tables to ai_service_role;
alter default privileges in schema ai
    grant usage, select on sequences to ai_service_role;

create table if not exists ai.analysis_runs (
    id uuid primary key default gen_random_uuid(),
    verification_id uuid not null,
    trace_id uuid,
    status text not null default 'running'
        check (status in ('running', 'completed', 'failed')),
    engine_version text,
    model text,
    tokens_in integer not null default 0 check (tokens_in >= 0),
    tokens_out integer not null default 0 check (tokens_out >= 0),
    cost_usd numeric(12, 6) not null default 0,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    error_code text
);

create index if not exists analysis_runs_verification_idx
    on ai.analysis_runs (verification_id, started_at desc);

create table if not exists ai.agent_traces (
    run_id uuid not null references ai.analysis_runs (id) on delete cascade,
    seq integer not null,
    node text not null,
    tool text,
    summary jsonb not null default '{}'::jsonb,
    duration_ms integer,
    created_at timestamptz not null default now(),
    primary key (run_id, seq)
);

create table if not exists ai.document_extractions (
    id uuid primary key default gen_random_uuid(),
    document_id uuid not null,
    run_id uuid not null references ai.analysis_runs (id) on delete cascade,
    page integer not null check (page >= 1),
    text_redacted text not null default '',
    fields jsonb not null default '{}'::jsonb,
    confidence numeric(4, 3) check (confidence between 0 and 1),
    created_at timestamptz not null default now(),
    unique (run_id, document_id, page)
);

create index if not exists document_extractions_document_idx
    on ai.document_extractions (document_id);

create table if not exists ai.event_dedupe (
    consumer text not null,
    event_id uuid not null,
    processed_at timestamptz not null default now(),
    primary key (consumer, event_id)
);

grant select, insert, update, delete on all tables in schema ai to ai_service_role;
grant usage, select on all sequences in schema ai to ai_service_role;
-- The migration registry is admin-only.
revoke all on ai.schema_migrations from ai_service_role;
