-- 011_security_hardening.sql
-- Workers keep read access through RLS; every write goes through core-api so
-- validation, ownership and state-machine rules cannot be bypassed.

-- Storage: only the backend (service role) writes document objects.
drop policy if exists documents_objects_insert on storage.objects;
drop policy if exists documents_objects_update on storage.objects;
drop policy if exists documents_objects_delete on storage.objects;

-- Core tables: drop direct worker writes that could forge status, risk or paths.
drop policy if exists verifications_insert_self on core.verifications;
drop policy if exists documents_insert_self on core.documents;
drop policy if exists documents_update_self on core.documents;
drop policy if exists documents_delete_self on core.documents;
drop policy if exists journeys_insert_self on core.migration_journeys;
drop policy if exists journeys_update_self on core.migration_journeys;
drop policy if exists checkins_update_self on core.checkins;
drop policy if exists complaints_insert_self on core.complaints;
drop policy if exists complaints_update_own_draft on core.complaints;
drop policy if exists complaint_documents_insert_self on core.complaint_documents;
