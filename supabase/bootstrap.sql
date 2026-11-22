-- Supabase bootstrap for core-api (run once as a superuser after `supabase start`).
--
--   psql "$DATABASE_URL" -f supabase/bootstrap.sql
--
-- It creates the service schema/role and grants only the `core` schema.
-- Set the role password out-of-band; never commit it.

create schema if not exists core;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'core_api_role') then
        create role core_api_role login;
    end if;
end $$;

grant usage, create on schema core to core_api_role;
grant usage on schema public to core_api_role;

-- The migration runner (running as the admin role) creates tables; the
-- service role gets table privileges in 008_rls.sql.

-- Other services own their own schemas and roles. core-api must never be
-- granted access to them.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'ai_service_role') then
        create role ai_service_role nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'notification_service_role') then
        create role notification_service_role nologin;
    end if;
end $$;
