-- 002_agencies.sql
-- SLBFE agency snapshots, canonical agencies and license history.

create table if not exists core.agency_snapshots (
    id uuid primary key default gen_random_uuid(),
    snapshot_date date not null,
    source_url text,
    checksum text not null,
    record_count integer not null default 0,
    imported_by uuid references core.users(id) on delete set null,
    imported_at timestamptz not null default now(),
    unique (snapshot_date, checksum)
);

create table if not exists core.agencies (
    id uuid primary key default gen_random_uuid(),
    registration_no text not null unique,
    name text not null,
    normalized_name text not null,
    license_no text,
    license_status core.agency_license_status not null default 'unknown',
    license_expires_on date,
    address text,
    district text,
    phone text,
    email text,
    latest_snapshot_id uuid references core.agency_snapshots(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists agencies_name_trgm_idx
    on core.agencies using gin (normalized_name gin_trgm_ops);
create index if not exists agencies_license_status_idx
    on core.agencies (license_status);
create index if not exists agencies_district_idx
    on core.agencies (district);

drop trigger if exists agencies_set_updated_at on core.agencies;
create trigger agencies_set_updated_at
before update on core.agencies
for each row execute function core.set_updated_at();

create table if not exists core.agency_license_history (
    id uuid primary key default gen_random_uuid(),
    agency_id uuid not null references core.agencies(id) on delete cascade,
    snapshot_id uuid references core.agency_snapshots(id) on delete set null,
    license_no text,
    status core.agency_license_status not null default 'unknown',
    issued_on date,
    expires_on date,
    job_categories text[],
    raw_data jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (agency_id, snapshot_id, license_no)
);

create index if not exists agency_license_history_agency_idx
    on core.agency_license_history (agency_id, created_at desc);
