-- 001_schema.sql
-- notification schema, least-privilege runtime role, and updated_at trigger.

create schema if not exists notification;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'notification_service_role') then
        create role notification_service_role nologin;
    end if;
end $$;

revoke all on schema notification from public;
grant usage on schema notification to notification_service_role;

alter default privileges in schema notification
    grant select, insert, update, delete on tables to notification_service_role;
alter default privileges in schema notification
    grant usage, select on sequences to notification_service_role;

create or replace function notification.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;
