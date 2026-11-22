-- 008_rls.sql
-- Defense-in-depth policies for direct Supabase access. The backend connects
-- with the trusted `core_api_role`; clients use `authenticated` + Supabase JWT.

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'core_api_role') then
        create role core_api_role nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
end $$;

do $$
begin
    if to_regprocedure('auth.uid()') is null then
        execute $fn$
            create function auth.uid() returns uuid
            language sql stable
            as $body$
                select coalesce(
                    nullif(current_setting('request.jwt.claim.sub', true), ''),
                    nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'
                )::uuid
            $body$;
        $fn$;
    end if;
end $$;

create or replace function core.current_user_id()
returns uuid
language sql
stable
as $$
    select auth.uid();
$$;

create or replace function core.current_user_role()
returns core.user_role
language sql
stable
security definer
set search_path = core, public, pg_temp
as $$
    select role from core.users where id = auth.uid();
$$;

create or replace function core.is_staff()
returns boolean
language sql
stable
security definer
set search_path = core, public, pg_temp
as $$
    select coalesce(
        (select role in ('caseworker', 'admin') from core.users where id = auth.uid()),
        false
    );
$$;

create or replace function core.is_admin()
returns boolean
language sql
stable
security definer
set search_path = core, public, pg_temp
as $$
    select coalesce(
        (select role = 'admin' from core.users where id = auth.uid()),
        false
    );
$$;

grant usage on schema core to core_api_role, authenticated;
grant select, insert, update, delete on all tables in schema core to core_api_role;
grant select, insert, update, delete on all tables in schema core to authenticated;
grant execute on function core.current_user_id() to authenticated, core_api_role;
grant execute on function core.current_user_role() to authenticated, core_api_role;
grant execute on function core.is_staff() to authenticated, core_api_role;
grant execute on function core.is_admin() to authenticated, core_api_role;

alter table core.users enable row level security;
alter table core.user_consents enable row level security;
alter table core.idempotency_keys enable row level security;
alter table core.outbox_events enable row level security;
alter table core.event_dedupe enable row level security;
alter table core.agency_snapshots enable row level security;
alter table core.agencies enable row level security;
alter table core.agency_license_history enable row level security;
alter table core.verifications enable row level security;
alter table core.documents enable row level security;
alter table core.migration_journeys enable row level security;
alter table core.checkins enable row level security;
alter table core.complaints enable row level security;
alter table core.complaint_documents enable row level security;
alter table core.case_notes enable row level security;
alter table core.notifications enable row level security;
alter table core.audit_logs enable row level security;

-- Backend role: full access to domain tables. audit_logs is immutable.
do $$
declare
    table_name text;
begin
    foreach table_name in array array[
        'users', 'user_consents', 'idempotency_keys', 'outbox_events', 'event_dedupe',
        'agency_snapshots', 'agencies', 'agency_license_history', 'verifications',
        'documents', 'migration_journeys', 'checkins', 'complaints',
        'complaint_documents', 'case_notes', 'notifications'
    ] loop
        execute format('drop policy if exists core_api_all on core.%I', table_name);
        execute format(
            'create policy core_api_all on core.%I for all to core_api_role using (true) with check (true)',
            table_name
        );
    end loop;
end $$;

drop policy if exists audit_logs_backend_select on core.audit_logs;
create policy audit_logs_backend_select on core.audit_logs
    for select to core_api_role using (true);
drop policy if exists audit_logs_backend_insert on core.audit_logs;
create policy audit_logs_backend_insert on core.audit_logs
    for insert to core_api_role with check (true);

-- users
drop policy if exists users_select_self_or_staff on core.users;
create policy users_select_self_or_staff on core.users
    for select to authenticated
    using (id = auth.uid() or core.is_staff());
drop policy if exists users_update_self on core.users;
create policy users_update_self on core.users
    for update to authenticated
    using (id = auth.uid())
    with check (id = auth.uid());
drop policy if exists users_admin_all on core.users;
create policy users_admin_all on core.users
    for all to authenticated
    using (core.is_admin())
    with check (core.is_admin());

-- consents
drop policy if exists consents_select on core.user_consents;
create policy consents_select on core.user_consents
    for select to authenticated
    using (user_id = auth.uid() or core.is_staff());
drop policy if exists consents_insert_self on core.user_consents;
create policy consents_insert_self on core.user_consents
    for insert to authenticated
    with check (user_id = auth.uid());
drop policy if exists consents_admin_all on core.user_consents;
create policy consents_admin_all on core.user_consents
    for all to authenticated
    using (core.is_admin())
    with check (core.is_admin());

-- idempotency keys are private to the caller
drop policy if exists idempotency_owner_all on core.idempotency_keys;
create policy idempotency_owner_all on core.idempotency_keys
    for all to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- agencies are readable by any signed-in user; writes are admin-only
drop policy if exists agencies_select_authenticated on core.agencies;
create policy agencies_select_authenticated on core.agencies
    for select to authenticated using (true);
drop policy if exists agencies_admin_all on core.agencies;
create policy agencies_admin_all on core.agencies
    for all to authenticated
    using (core.is_admin())
    with check (core.is_admin());
drop policy if exists agency_snapshots_select on core.agency_snapshots;
create policy agency_snapshots_select on core.agency_snapshots
    for select to authenticated using (true);
drop policy if exists agency_snapshots_admin_all on core.agency_snapshots;
create policy agency_snapshots_admin_all on core.agency_snapshots
    for all to authenticated
    using (core.is_admin())
    with check (core.is_admin());
drop policy if exists agency_license_history_select on core.agency_license_history;
create policy agency_license_history_select on core.agency_license_history
    for select to authenticated using (true);
drop policy if exists agency_license_history_admin_all on core.agency_license_history;
create policy agency_license_history_admin_all on core.agency_license_history
    for all to authenticated
    using (core.is_admin())
    with check (core.is_admin());

-- verifications
drop policy if exists verifications_select on core.verifications;
create policy verifications_select on core.verifications
    for select to authenticated
    using (user_id = auth.uid() or core.is_staff());
drop policy if exists verifications_insert_self on core.verifications;
create policy verifications_insert_self on core.verifications
    for insert to authenticated
    with check (user_id = auth.uid());
drop policy if exists verifications_staff_all on core.verifications;
create policy verifications_staff_all on core.verifications
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

-- documents
drop policy if exists documents_select on core.documents;
create policy documents_select on core.documents
    for select to authenticated
    using (user_id = auth.uid() or core.is_staff());
drop policy if exists documents_insert_self on core.documents;
create policy documents_insert_self on core.documents
    for insert to authenticated
    with check (user_id = auth.uid());
drop policy if exists documents_update_self on core.documents;
create policy documents_update_self on core.documents
    for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());
drop policy if exists documents_delete_self on core.documents;
create policy documents_delete_self on core.documents
    for delete to authenticated
    using (user_id = auth.uid());
drop policy if exists documents_staff_all on core.documents;
create policy documents_staff_all on core.documents
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

-- journeys
drop policy if exists journeys_select on core.migration_journeys;
create policy journeys_select on core.migration_journeys
    for select to authenticated
    using (user_id = auth.uid() or core.is_staff());
drop policy if exists journeys_insert_self on core.migration_journeys;
create policy journeys_insert_self on core.migration_journeys
    for insert to authenticated
    with check (user_id = auth.uid());
drop policy if exists journeys_update_self on core.migration_journeys;
create policy journeys_update_self on core.migration_journeys
    for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());
drop policy if exists journeys_staff_all on core.migration_journeys;
create policy journeys_staff_all on core.migration_journeys
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

-- check-ins
drop policy if exists checkins_select on core.checkins;
create policy checkins_select on core.checkins
    for select to authenticated
    using (user_id = auth.uid() or core.is_staff());
drop policy if exists checkins_update_self on core.checkins;
create policy checkins_update_self on core.checkins
    for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());
drop policy if exists checkins_staff_all on core.checkins;
create policy checkins_staff_all on core.checkins
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

-- complaints
drop policy if exists complaints_select on core.complaints;
create policy complaints_select on core.complaints
    for select to authenticated
    using (user_id = auth.uid() or core.is_staff());
drop policy if exists complaints_insert_self on core.complaints;
create policy complaints_insert_self on core.complaints
    for insert to authenticated
    with check (user_id = auth.uid());
drop policy if exists complaints_update_own_draft on core.complaints;
create policy complaints_update_own_draft on core.complaints
    for update to authenticated
    using (user_id = auth.uid() and status = 'draft')
    with check (user_id = auth.uid() and status = 'draft');
drop policy if exists complaints_staff_all on core.complaints;
create policy complaints_staff_all on core.complaints
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

drop policy if exists complaint_documents_select on core.complaint_documents;
create policy complaint_documents_select on core.complaint_documents
    for select to authenticated
    using (
        core.is_staff()
        or exists (
            select 1 from core.complaints c
            where c.id = complaint_id and c.user_id = auth.uid()
        )
    );
drop policy if exists complaint_documents_insert_self on core.complaint_documents;
create policy complaint_documents_insert_self on core.complaint_documents
    for insert to authenticated
    with check (
        exists (
            select 1 from core.complaints c
            where c.id = complaint_id and c.user_id = auth.uid()
        )
    );
drop policy if exists complaint_documents_staff_all on core.complaint_documents;
create policy complaint_documents_staff_all on core.complaint_documents
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

-- notes are staff-only
drop policy if exists case_notes_staff_all on core.case_notes;
create policy case_notes_staff_all on core.case_notes
    for all to authenticated
    using (core.is_staff())
    with check (core.is_staff());

-- in-app notifications: owner read/update only (writes come from the backend)
drop policy if exists notifications_select_self on core.notifications;
create policy notifications_select_self on core.notifications
    for select to authenticated
    using (user_id = auth.uid());
drop policy if exists notifications_update_self on core.notifications;
create policy notifications_update_self on core.notifications
    for update to authenticated
    using (user_id = auth.uid())
    with check (user_id = auth.uid());

-- audit logs are admin-readable and append-only from the backend
drop policy if exists audit_logs_admin_select on core.audit_logs;
create policy audit_logs_admin_select on core.audit_logs
    for select to authenticated
    using (core.is_admin());
