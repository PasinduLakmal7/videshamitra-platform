-- 004_journeys_checkins.sql

create table if not exists core.migration_journeys (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    agency_id uuid references core.agencies(id) on delete set null,
    destination_country text,
    employer_name text,
    job_title text,
    departure_date date,
    return_date date,
    stage core.journey_stage not null default 'pre_departure',
    consent_checkins boolean not null default false,
    consent_at timestamptz,
    next_checkin_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists migration_journeys_user_idx on core.migration_journeys (user_id);
create index if not exists migration_journeys_stage_idx on core.migration_journeys (stage);
create index if not exists migration_journeys_next_checkin_idx on core.migration_journeys (next_checkin_at);

drop trigger if exists migration_journeys_set_updated_at on core.migration_journeys;
create trigger migration_journeys_set_updated_at
before update on core.migration_journeys
for each row execute function core.set_updated_at();

create table if not exists core.checkins (
    id uuid primary key default gen_random_uuid(),
    journey_id uuid not null references core.migration_journeys(id) on delete cascade,
    user_id uuid not null references core.users(id) on delete cascade,
    due_at timestamptz not null,
    channel core.notification_channel not null default 'in_app',
    status core.checkin_status not null default 'scheduled',
    sent_at timestamptz,
    completed_at timestamptz,
    response jsonb,
    risk_level core.risk_level,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists checkins_journey_idx on core.checkins (journey_id);
create index if not exists checkins_status_due_idx on core.checkins (status, due_at);
create index if not exists checkins_user_created_idx on core.checkins (user_id, created_at desc);

drop trigger if exists checkins_set_updated_at on core.checkins;
create trigger checkins_set_updated_at
before update on core.checkins
for each row execute function core.set_updated_at();
