-- 010_indexes.sql
-- Composite/partial indexes that encode domain invariants or hot queries.

-- One active journey per worker.
create unique index if not exists migration_journeys_one_active_idx
    on core.migration_journeys (user_id)
    where stage <> 'returned';

-- A journey cannot schedule the same check-in time twice.
create unique index if not exists checkins_journey_due_unique_idx
    on core.checkins (journey_id, due_at);

-- Duplicate uploads are rejected per user while the document is live.
create unique index if not exists documents_user_sha_live_idx
    on core.documents (user_id, sha256)
    where deleted_at is null;

-- Hot admin queues.
create index if not exists complaints_open_tier_idx
    on core.complaints (triage_tier, created_at desc)
    where status not in ('resolved', 'closed');
create index if not exists checkins_due_pending_idx
    on core.checkins (due_at)
    where status in ('scheduled', 'sent');
create index if not exists verifications_processing_stale_idx
    on core.verifications (updated_at)
    where status = 'processing';
create index if not exists verifications_high_risk_idx
    on core.verifications (created_at desc)
    where risk_level in ('high', 'critical');
create index if not exists notifications_unread_idx
    on core.notifications (user_id, created_at desc)
    where read_at is null;
create index if not exists notifications_data_gin_idx
    on core.notifications using gin (data jsonb_path_ops);
create index if not exists outbox_pending_idx
    on core.outbox_events (available_at)
    where status = 'pending';
create index if not exists idempotency_expires_idx
    on core.idempotency_keys (expires_at);
create index if not exists agency_snapshots_date_idx
    on core.agency_snapshots (snapshot_date desc);
create index if not exists users_role_active_idx
    on core.users (role, is_active);
create index if not exists complaint_documents_document_idx
    on core.complaint_documents (document_id);
