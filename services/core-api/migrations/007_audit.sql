-- 007_audit.sql
-- Immutable audit trail for sensitive staff/system actions.

create table if not exists core.audit_logs (
    id uuid primary key default gen_random_uuid(),
    actor_id uuid references core.users(id) on delete set null,
    actor_role core.user_role,
    action text not null,
    entity_type text,
    entity_id uuid,
    ip_address inet,
    user_agent text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists audit_logs_actor_idx on core.audit_logs (actor_id);
create index if not exists audit_logs_entity_idx on core.audit_logs (entity_type, entity_id);
create index if not exists audit_logs_created_idx on core.audit_logs (created_at desc);
