-- 009_storage.sql
-- Private `documents` bucket and path-based storage policies.
-- Path convention: {user_id}/{document_id}/{filename}

do $$
begin
    if to_regclass('storage.buckets') is null then
        create schema if not exists storage;
        create table storage.buckets (
            id text primary key,
            name text not null,
            public boolean not null default false,
            file_size_limit bigint,
            allowed_mime_types text[],
            created_at timestamptz not null default now()
        );
        create table storage.objects (
            id uuid primary key default gen_random_uuid(),
            bucket_id text references storage.buckets(id),
            name text not null,
            owner uuid,
            metadata jsonb,
            created_at timestamptz not null default now(),
            updated_at timestamptz not null default now()
        );
        alter table storage.objects enable row level security;
    end if;
end $$;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
    'documents',
    'documents',
    false,
    26214400,
    array['application/pdf', 'image/jpeg', 'image/png']
)
on conflict (id) do update
set public = false,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

-- The bucket is private; object access is scoped by the first path segment.
drop policy if exists documents_objects_select on storage.objects;
create policy documents_objects_select on storage.objects
    for select to authenticated
    using (
        bucket_id = 'documents'
        and (split_part(name, '/', 1) = auth.uid()::text or core.is_staff())
    );

drop policy if exists documents_objects_insert on storage.objects;
create policy documents_objects_insert on storage.objects
    for insert to authenticated
    with check (
        bucket_id = 'documents'
        and split_part(name, '/', 1) = auth.uid()::text
    );

drop policy if exists documents_objects_update on storage.objects;
create policy documents_objects_update on storage.objects
    for update to authenticated
    using (
        bucket_id = 'documents'
        and split_part(name, '/', 1) = auth.uid()::text
    )
    with check (
        bucket_id = 'documents'
        and split_part(name, '/', 1) = auth.uid()::text
    );

drop policy if exists documents_objects_delete on storage.objects;
create policy documents_objects_delete on storage.objects
    for delete to authenticated
    using (
        bucket_id = 'documents'
        and split_part(name, '/', 1) = auth.uid()::text
    );
