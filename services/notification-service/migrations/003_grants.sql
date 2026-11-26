-- 003_grants.sql
-- Runtime role: DML on notification tables only; the migration registry is admin-only.

grant select, insert, update, delete on all tables in schema notification
    to notification_service_role;
grant usage, select on all sequences in schema notification
    to notification_service_role;
revoke all on notification.schema_migrations from notification_service_role;
