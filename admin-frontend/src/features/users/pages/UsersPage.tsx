import React, { useCallback, useEffect, useState } from 'react';
import { UserCog } from 'lucide-react';
import { api, errorMessage } from '@/lib/api-client';
import { formatDate, titleCase } from '@/lib/format';
import type { Role, User } from '@/types/models';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/Modal';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Input, Select } from '@/components/ui/Input';
import { ErrorState } from '@/components/ui/LoadingSpinner';
import { Pagination } from '@/components/ui/Pagination';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';

const roleOptions = [
  { value: '', label: 'All roles' },
  { value: 'worker', label: 'Worker' },
  { value: 'caseworker', label: 'Caseworker' },
  { value: 'admin', label: 'Admin' },
];

const editRoleOptions = roleOptions.filter((option) => option.value);

type PendingAction =
  | { kind: 'role'; user: User; role: Role }
  | { kind: 'status'; user: User; isActive: boolean };

export const UsersPage: React.FC = () => {
  const { push } = useToast();
  const [rows, setRows] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [role, setRole] = useState('');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.page<User>('/users', {
        page,
        page_size: 20,
        role,
        q: search,
        sort: 'created_at',
        order: 'desc',
      });
      setRows(result.items);
      setTotal(result.meta.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, role, search]);

  useEffect(() => {
    void load();
  }, [load]);

  const confirm = async () => {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending.kind === 'role') {
        await api.patch(`/users/${pending.user.id}/role`, { role: pending.role });
        push('Role updated');
      } else {
        await api.patch(`/users/${pending.user.id}/status`, { is_active: pending.isActive });
        push(pending.isActive ? 'Account activated' : 'Account deactivated');
      }
      setPending(null);
      await load();
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const columns: Column<User>[] = [
    {
      key: 'full_name',
      header: 'Name',
      render: (row) => (
        <div className="cell-stack">
          <strong>{row.full_name ?? '—'}</strong>
          <span className="muted">{row.phone ?? ''}</span>
        </div>
      ),
    },
    {
      key: 'role',
      header: 'Role',
      render: (row) => (
        <select
          className="inline-select"
          value={row.role}
          onChange={(event) =>
            setPending({ kind: 'role', user: row, role: event.target.value as Role })
          }
        >
          {editRoleOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ),
    },
    { key: 'preferred_language', header: 'Language', render: (row) => row.preferred_language.toUpperCase() },
    {
      key: 'is_active',
      header: 'Status',
      render: (row) => <StatusBadge status={row.is_active ? 'active' : 'cancelled'} label={row.is_active ? 'Active' : 'Inactive'} />,
    },
    { key: 'created_at', header: 'Joined', render: (row) => formatDate(row.created_at) },
    {
      key: 'actions',
      header: '',
      render: (row) => (
        <Button
          size="sm"
          variant={row.is_active ? 'danger' : 'secondary'}
          onClick={() => setPending({ kind: 'status', user: row, isActive: !row.is_active })}
        >
          {row.is_active ? 'Deactivate' : 'Activate'}
        </Button>
      ),
    },
  ];

  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <h1>Users</h1>
          <p>Worker, caseworker and administrator accounts.</p>
        </div>
        <span className="heading-note"><UserCog size={16} /> Admin only</span>
      </div>

      <div className="card filter-bar">
        <form
          className="filter-form"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setSearch(query.trim());
          }}
        >
          <Input
            label="Search"
            name="q"
            value={query}
            placeholder="Name or phone"
            onChange={(event) => setQuery(event.target.value)}
          />
          <Select
            label="Role"
            name="role"
            value={role}
            options={roleOptions}
            onChange={(event) => {
              setRole(event.target.value);
              setPage(1);
            }}
          />
          <div className="filter-actions">
            <Button type="submit" size="sm">Apply</Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => {
                setQuery('');
                setSearch('');
                setRole('');
                setPage(1);
              }}
            >
              Reset
            </Button>
          </div>
        </form>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <>
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(row) => row.id}
            loading={loading}
            emptyMessage="No users match these filters."
          />
          <Pagination page={page} pageSize={20} total={total} onPageChange={setPage} />
        </>
      )}

      <ConfirmDialog
        open={Boolean(pending)}
        title={pending?.kind === 'role' ? 'Change role?' : pending?.isActive ? 'Activate account?' : 'Deactivate account?'}
        message={
          pending?.kind === 'role'
            ? `Change ${pending.user.full_name ?? pending.user.id} to ${titleCase(pending.role)}?`
            : `This will ${pending?.isActive ? 'allow' : 'block'} sign-in for ${pending?.user.full_name ?? pending?.user.id}.`
        }
        confirmLabel="Confirm"
        busy={busy}
        onCancel={() => setPending(null)}
        onConfirm={confirm}
      />
    </div>
  );
};
