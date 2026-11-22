-- 005_complaints_cases.sql

create table if not exists core.complaints (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    journey_id uuid references core.migration_journeys(id) on delete set null,
    verification_id uuid references core.verifications(id) on delete set null,
    agency_id uuid references core.agencies(id) on delete set null,
    checkin_id uuid references core.checkins(id) on delete set null,
    title text not null,
    description text,
    status core.complaint_status not null default 'draft',
    triage_tier smallint not null default 1 check (triage_tier between 1 and 3),
    assigned_to uuid references core.users(id) on delete set null,
    evidence jsonb not null default '[]'::jsonb,
    draft_text text,
    submitted_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists complaints_user_created_idx
    on core.complaints (user_id, created_at desc);
create index if not exists complaints_status_idx on core.complaints (status);
create index if not exists complaints_assigned_to_idx on core.complaints (assigned_to);
create index if not exists complaints_triage_tier_idx on core.complaints (triage_tier);

drop trigger if exists complaints_set_updated_at on core.complaints;
create trigger complaints_set_updated_at
before update on core.complaints
for each row execute function core.set_updated_at();

create table if not exists core.complaint_documents (
    complaint_id uuid not null references core.complaints(id) on delete cascade,
    document_id uuid not null references core.documents(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (complaint_id, document_id)
);

create table if not exists core.case_notes (
    id uuid primary key default gen_random_uuid(),
    complaint_id uuid not null references core.complaints(id) on delete cascade,
    author_id uuid references core.users(id) on delete set null,
    body text not null,
    is_internal boolean not null default true,
    created_at timestamptz not null default now()
);

create index if not exists case_notes_complaint_idx
    on core.case_notes (complaint_id, created_at);
