-- 006_notifications.sql
-- In-app feed only. Device tokens, preferences and delivery live in
-- notification-service and are never stored here.

create table if not exists core.notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references core.users(id) on delete cascade,
    type core.notification_type not null,
    title text not null,
    body text not null,
    data jsonb not null default '{}'::jsonb,
    deep_link text,
    read_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists notifications_user_created_idx
    on core.notifications (user_id, created_at desc);
create index if not exists notifications_user_read_idx
    on core.notifications (user_id, read_at);
