-- 003_verifications_documents.sql

create table if not exists core.verifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    agency_id uuid references core.agencies(id) on delete set null,
    agency_name_input text,
    job_title text,
    employer_name text,
    destination_country text,
    offered_salary numeric(14, 2),
    currency text,
    status core.verification_status not null default 'pending',
    risk_level core.risk_level,
    risk_score integer check (risk_score is null or (risk_score >= 0 and risk_score <= 100)),
    findings jsonb not null default '[]'::jsonb,
    evidence jsonb not null default '[]'::jsonb,
    engine_version text,
    analysis_run_id text,
    failure_code text,
    failure_message text,
    retry_count integer not null default 0,
    reviewed_by uuid references core.users(id) on delete set null,
    reviewed_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    completed_at timestamptz
);

create index if not exists verifications_user_created_idx
    on core.verifications (user_id, created_at desc);
create index if not exists verifications_status_idx on core.verifications (status);
create index if not exists verifications_risk_level_idx on core.verifications (risk_level);

drop trigger if exists verifications_set_updated_at on core.verifications;
create trigger verifications_set_updated_at
before update on core.verifications
for each row execute function core.set_updated_at();

create table if not exists core.documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    verification_id uuid references core.verifications(id) on delete set null,
    type core.document_type not null default 'other',
    status core.document_status not null default 'uploaded',
    storage_path text not null,
    original_filename text not null,
    mime_type text not null,
    size_bytes bigint not null check (size_bytes >= 0),
    page_count integer,
    sha256 text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    deleted_at timestamptz
);

create index if not exists documents_user_created_idx
    on core.documents (user_id, created_at desc);
create index if not exists documents_verification_idx on core.documents (verification_id);
create index if not exists documents_sha256_idx on core.documents (sha256);
create index if not exists documents_deleted_at_idx on core.documents (deleted_at);

drop trigger if exists documents_set_updated_at on core.documents;
create trigger documents_set_updated_at
before update on core.documents
for each row execute function core.set_updated_at();
