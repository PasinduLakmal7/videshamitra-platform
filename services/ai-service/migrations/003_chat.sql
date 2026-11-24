-- 003_chat.sql
-- Chat sessions and messages. Only redacted text is stored; retention sweeps use created_at.

create table if not exists ai.chat_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    title text,
    language text not null default 'en' check (language in ('en', 'si', 'ta')),
    locked boolean not null default false,
    triage_tier smallint check (triage_tier between 1 and 3),
    created_at timestamptz not null default now(),
    last_message_at timestamptz not null default now()
);

create index if not exists chat_sessions_user_idx
    on ai.chat_sessions (user_id, last_message_at desc);
create index if not exists chat_sessions_retention_idx
    on ai.chat_sessions (last_message_at);

create table if not exists ai.chat_messages (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references ai.chat_sessions (id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system', 'tool')),
    content_redacted text not null,
    citations jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists chat_messages_session_idx
    on ai.chat_messages (session_id, created_at);
create index if not exists chat_messages_retention_idx
    on ai.chat_messages (created_at);
