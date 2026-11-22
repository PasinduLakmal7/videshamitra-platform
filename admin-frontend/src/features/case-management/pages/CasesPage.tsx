import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, errorMessage } from '@/lib/api-client';
import { formatDate } from '@/lib/format';
import type { Complaint } from '@/types/models';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Input, Select } from '@/components/ui/Input';
import { ErrorState } from '@/components/ui/LoadingSpinner';
import { Pagination } from '@/components/ui/Pagination';
import { StatusBadge } from '@/components/ui/StatusBadge';

const statusOptions = [
  { value: '', label: 'All statuses' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'under_review', label: 'Under review' },
  { value: 'escalated', label: 'Escalated' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
];

const tierOptions = [
  { value: '', label: 'All tiers' },
  { value: '1', label: 'Tier 1' },
  { value: '2', label: 'Tier 2' },
  { value: '3', label: 'Tier 3' },
];

export const CasesPage: React.FC = () => {
  const navigate = useNavigate();
  const [rows, setRows] = useState<Complaint[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [tier, setTier] = useState('');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.page<Complaint>('/admin/cases', {
        page,
        page_size: 20,
        status,
        triage_tier: tier,
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
  }, [page, status, tier, search]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: Column<Complaint>[] = [
    {
      key: 'title',
      header: 'Case',
      render: (row) => (
        <div className="cell-stack">
          <strong>{row.title}</strong>
          <span className="muted">#{row.id.slice(0, 8)}</span>
        </div>
      ),
    },
    {
      key: 'worker_name',
      header: 'Worker',
      render: (row) => (
        <div className="cell-stack">
          <span>{row.worker_name ?? '—'}</span>
          <span className="muted">{row.worker_phone ?? ''}</span>
        </div>
      ),
    },
    {
      key: 'agency_name',
      header: 'Agency',
      render: (row) => row.agency_name ?? '—',
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'triage_tier',
      header: 'Tier',
      render: (row) => <span className={`tier-chip tier-${row.triage_tier}`}>T{row.triage_tier}</span>,
    },
    {
      key: 'submitted_at',
      header: 'Submitted',
      render: (row) => formatDate(row.submitted_at ?? row.created_at),
    },
  ];

  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <h1>Case queue</h1>
          <p>Review worker complaints, evidence and escalations.</p>
        </div>
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
            placeholder="Title, worker or description"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <Select
            label="Status"
            name="status"
            value={status}
            options={statusOptions}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          />
          <Select
            label="Tier"
            name="tier"
            value={tier}
            options={tierOptions}
            onChange={(event) => {
              setTier(event.target.value);
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
                setStatus('');
                setTier('');
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
            emptyMessage="No cases match these filters."
            onRowClick={(row) => navigate(`/cases/${row.id}`)}
          />
          <Pagination page={page} pageSize={20} total={total} onPageChange={setPage} />
        </>
      )}
    </div>
  );
};
