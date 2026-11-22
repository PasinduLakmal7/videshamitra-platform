import React, { useCallback, useEffect, useState } from 'react';
import { ScrollText } from 'lucide-react';
import { api, errorMessage } from '@/lib/api-client';
import { formatDate } from '@/lib/format';
import type { AuditLog } from '@/types/models';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Input } from '@/components/ui/Input';
import { ErrorState } from '@/components/ui/LoadingSpinner';
import { Modal } from '@/components/ui/Modal';
import { Pagination } from '@/components/ui/Pagination';

export const AuditPage: React.FC = () => {
  const [rows, setRows] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [actionInput, setActionInput] = useState('');
  const [entityInput, setEntityInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<AuditLog | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.page<AuditLog>('/admin/audit-logs', {
        page,
        page_size: 25,
        action,
        entity_type: entityType,
      });
      setRows(result.items);
      setTotal(result.meta.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, action, entityType]);

  useEffect(() => {
    void load();
  }, [load]);

  const columns: Column<AuditLog>[] = [
    { key: 'created_at', header: 'When', render: (row) => formatDate(row.created_at) },
    { key: 'action', header: 'Action', render: (row) => <code className="code">{row.action}</code> },
    {
      key: 'actor',
      header: 'Actor',
      render: (row) => (
        <div className="cell-stack">
          <span>{row.actor_id ? row.actor_id.slice(0, 8) : 'system'}</span>
          <span className="muted">{row.actor_role ?? 'service'}</span>
        </div>
      ),
    },
    {
      key: 'entity',
      header: 'Entity',
      render: (row) => (
        <div className="cell-stack">
          <span>{row.entity_type ?? '—'}</span>
          <span className="muted">{row.entity_id ? row.entity_id.slice(0, 8) : ''}</span>
        </div>
      ),
    },
    { key: 'ip_address', header: 'IP', render: (row) => row.ip_address ?? '—' },
  ];

  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <h1>Audit log</h1>
          <p>Append-only trail of sensitive staff and system actions.</p>
        </div>
        <span className="heading-note"><ScrollText size={16} /> Admin only</span>
      </div>

      <div className="card filter-bar">
        <form
          className="filter-form"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setAction(actionInput.trim());
            setEntityType(entityInput.trim());
          }}
        >
          <Input
            label="Action"
            name="action"
            value={actionInput}
            placeholder="e.g. case.escalated"
            onChange={(event) => setActionInput(event.target.value)}
          />
          <Input
            label="Entity type"
            name="entity_type"
            value={entityInput}
            placeholder="e.g. complaint"
            onChange={(event) => setEntityInput(event.target.value)}
          />
          <div className="filter-actions">
            <Button type="submit" size="sm">Apply</Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => {
                setActionInput('');
                setEntityInput('');
                setAction('');
                setEntityType('');
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
            emptyMessage="No audit entries match these filters."
            onRowClick={setSelected}
          />
          <Pagination page={page} pageSize={25} total={total} onPageChange={setPage} />
        </>
      )}

      <Modal
        open={Boolean(selected)}
        title="Audit entry"
        onClose={() => setSelected(null)}
        footer={<Button variant="secondary" onClick={() => setSelected(null)}>Close</Button>}
      >
        {selected && (
          <div className="stack-sm">
            <div className="detail-grid">
              <div><span>Action</span><strong>{selected.action}</strong></div>
              <div><span>When</span><strong>{formatDate(selected.created_at)}</strong></div>
              <div><span>Actor</span><strong>{selected.actor_id ?? 'system'}</strong></div>
              <div><span>Role</span><strong>{selected.actor_role ?? '—'}</strong></div>
              <div><span>Entity</span><strong>{selected.entity_type ?? '—'}</strong></div>
              <div><span>Entity ID</span><strong>{selected.entity_id ?? '—'}</strong></div>
            </div>
            <h3>Metadata</h3>
            <pre className="json-block">{JSON.stringify(selected.metadata, null, 2)}</pre>
          </div>
        )}
      </Modal>
    </div>
  );
};
