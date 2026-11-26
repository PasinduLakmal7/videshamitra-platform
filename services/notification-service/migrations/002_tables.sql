-- 002_tables.sql
-- Device tokens, preferences, deliveries, attempts, and consumer dedupe.

create table if not exists notification.event_dedupe (
    consumer text not null,
    event_id uuid not null,
    event_type text not null,
    notification_id uuid,
    processed_at timestamptz not null default now(),
    primary key (consumer, event_id)
);

create index if not exists event_dedupe_processed_idx
    on notification.event_dedupe (processed_at);

create table if not exists notification.device_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    token text not null,
    platform text not null check (platform in ('android', 'ios', 'web')),
    app_version text,
    device_id text,
    locale text,
    is_active boolean not null default true,
    last_seen_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint device_tokens_token_key unique (token),
    constraint device_tokens_token_length check (char_length(token) between 1 and 512)
);

create index if not exists device_tokens_user_active_idx
    on notification.device_tokens (user_id, is_active);

create table if not exists notification.notification_preferences (
    user_id uuid primary key,
    channels jsonb not null default
        '{"push": true, "whatsapp": false, "email": false, "sms": false}'::jsonb,
    quiet_hours_start time,
    quiet_hours_end time,
    timezone text not null default 'Asia/Colombo',
    locale text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint notification_preferences_quiet_hours_pair
        check ((quiet_hours_start is null) = (quiet_hours_end is null))
);

create table if not exists notification.deliveries (
    id uuid primary key default gen_random_uuid(),
    notification_id uuid not null,
    user_id uuid not null,
    notification_type text not null,
    locale text not null default 'en',
    title text not null,
    body text not null,
    deep_link text,
    payload jsonb not null default '{}'::jsonb,
    channel text not null check (channel in ('push', 'whatsapp', 'email', 'sms')),
    device_token_id uuid references notification.device_tokens (id) on delete cascade,
    status text not null default 'pending'
        check (status in ('pending', 'sending', 'sent', 'failed', 'skipped')),
    pending_reason text
        check (pending_reason in ('new', 'retry', 'quiet_hours')),
    attempt_count integer not null default 0 check (attempt_count >= 0),
    next_attempt_at timestamptz not null default now(),
    provider_message_id text,
    last_error_code text,
    last_error text,
    sent_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists deliveries_device_target_key
    on notification.deliveries (notification_id, channel, device_token_id)
    where device_token_id is not null;

create unique index if not exists deliveries_channel_target_key
    on notification.deliveries (notification_id, channel)
    where device_token_id is null;

create index if not exists deliveries_due_idx
    on notification.deliveries (status, next_attempt_at)
    where status = 'pending';

create index if not exists deliveries_user_created_idx
    on notification.deliveries (user_id, created_at desc);

create index if not exists deliveries_notification_idx
    on notification.deliveries (notification_id);

create table if not exists notification.delivery_attempts (
    id uuid primary key default gen_random_uuid(),
    delivery_id uuid not null references notification.deliveries (id) on delete cascade,
    attempt_number integer not null check (attempt_number >= 1),
    provider text not null check (provider in ('stub', 'fcm', 'whatsapp')),
    status text not null check (status in ('sent', 'retryable', 'permanent')),
    http_status integer,
    provider_message_id text,
    error_code text,
    error_message text,
    created_at timestamptz not null default now(),
    constraint delivery_attempts_number_key unique (delivery_id, attempt_number)
);

create index if not exists delivery_attempts_delivery_idx
    on notification.delivery_attempts (delivery_id);

drop trigger if exists device_tokens_touch_updated_at on notification.device_tokens;
create trigger device_tokens_touch_updated_at
before update on notification.device_tokens
for each row execute function notification.touch_updated_at();

drop trigger if exists notification_preferences_touch_updated_at
    on notification.notification_preferences;
create trigger notification_preferences_touch_updated_at
before update on notification.notification_preferences
for each row execute function notification.touch_updated_at();

drop trigger if exists deliveries_touch_updated_at on notification.deliveries;
create trigger deliveries_touch_updated_at
before update on notification.deliveries
for each row execute function notification.touch_updated_at();
