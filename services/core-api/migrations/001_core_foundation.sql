-- 001_core_foundation.sql
-- Extensions, enums, identity tables, idempotency, outbox/dedupe and triggers.

create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create schema if not exists core;

-- Local/CI stub for auth so migrations work without the Supabase stack.
do $$
begin
    if to_regclass('auth.users') is null then
        create schema if not exists auth;
        create table auth.users (
            id uuid primary key,
            email text,
            phone text,
            raw_user_meta_data jsonb not null default '{}'::jsonb,
            created_at timestamptz not null default now()
        );
    end if;
end $$;

do $$
begin
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'user_role') then
        create type core.user_role as enum ('worker', 'caseworker', 'admin');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'language_code') then
        create type core.language_code as enum ('en', 'si', 'ta');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'consent_type') then
        create type core.consent_type as enum ('data_processing', 'checkins', 'whatsapp');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'agency_license_status') then
        create type core.agency_license_status as enum ('active', 'suspended', 'expired', 'cancelled', 'unknown');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'verification_status') then
        create type core.verification_status as enum ('pending', 'processing', 'verified', 'suspicious', 'fraudulent', 'failed');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'risk_level') then
        create type core.risk_level as enum ('low', 'medium', 'high', 'critical');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'document_type') then
        create type core.document_type as enum ('job_offer', 'employment_contract', 'passport', 'visa', 'payment_receipt', 'screenshot', 'other');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'document_status') then
        create type core.document_status as enum ('uploaded', 'processing', 'processed', 'failed');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'journey_stage') then
        create type core.journey_stage as enum ('pre_departure', 'employed_abroad', 'returned');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'checkin_status') then
        create type core.checkin_status as enum ('scheduled', 'sent', 'completed', 'missed', 'escalated');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'complaint_status') then
        create type core.complaint_status as enum ('draft', 'submitted', 'under_review', 'escalated', 'resolved', 'closed');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'notification_type') then
        create type core.notification_type as enum ('checkin_due', 'checkin_missed', 'agency_license_changed', 'verification_complete', 'complaint_update', 'caseworker_message', 'system');
    end if;
    if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace
                   where n.nspname = 'core' and t.typname = 'notification_channel') then
        create type core.notification_channel as enum ('in_app', 'push', 'whatsapp', 'email', 'sms');
    end if;
end $$;

create or replace function core.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

create table if not exists core.users (
    id uuid primary key references auth.users(id) on delete cascade,
    role core.user_role not null default 'worker',
    full_name text,
    phone text,
    preferred_language core.language_code not null default 'en',
    country_of_work text,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create or replace function core.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = core, public, pg_temp
as $$
declare
    lang core.language_code := 'en';
begin
    if new.raw_user_meta_data->>'preferred_language' in ('en', 'si', 'ta') then
        lang := (new.raw_user_meta_data->>'preferred_language')::core.language_code;
    end if;
    insert into core.users (id, full_name, phone, preferred_language, country_of_work)
    values (
        new.id,
        nullif(new.raw_user_meta_data->>'full_name', ''),
        new.phone,
        lang,
        nullif(new.raw_user_meta_data->>'country_of_work', '')
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function core.handle_new_auth_user();

create or replace function core.protect_user_privileges()
returns trigger
language plpgsql
as $$
begin
    if (new.role is distinct from old.role or new.is_active is distinct from old.is_active)
       and current_user not in ('postgres', 'core_api_role', 'service_role', 'supabase_admin') then
        raise exception 'role and is_active can only be changed by the backend'
            using errcode = '42501';
    end if;
    return new;
end;
$$;

drop trigger if exists users_protect_privileges on core.users;
create trigger users_protect_privileges
before update on core.users
for each row execute function core.protect_user_privileges();

drop trigger if exists users_set_updated_at on core.users;
create trigger users_set_updated_at
before update on core.users
for each row execute function core.set_updated_at();

create table if not exists core.user_consents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    type core.consent_type not null,
    granted boolean not null,
    version text not null default '1',
    granted_at timestamptz,
    revoked_at timestamptz,
    ip_address inet,
    user_agent text,
    created_at timestamptz not null default now()
);

create index if not exists user_consents_user_type_idx
    on core.user_consents (user_id, type, created_at desc);

create table if not exists core.idempotency_keys (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    key text not null,
    method text not null,
    path text not null,
    request_hash text not null,
    status_code integer not null default 0,
    response_body jsonb,
    created_at timestamptz not null default now(),
    expires_at timestamptz not null default now() + interval '24 hours',
    unique (user_id, key)
);

create table if not exists core.outbox_events (
    id uuid primary key default gen_random_uuid(),
    event_id uuid not null unique,
    event_type text not null,
    version integer not null default 1,
    stream text not null,
    payload jsonb not null,
    status text not null default 'pending' check (status in ('pending', 'published', 'failed')),
    attempts integer not null default 0,
    available_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    published_at timestamptz,
    last_error text
);

create index if not exists outbox_events_status_available_idx
    on core.outbox_events (status, available_at);

create table if not exists core.event_dedupe (
    id uuid primary key default gen_random_uuid(),
    consumer text not null,
    event_id uuid not null,
    processed_at timestamptz not null default now(),
    unique (consumer, event_id)
);
