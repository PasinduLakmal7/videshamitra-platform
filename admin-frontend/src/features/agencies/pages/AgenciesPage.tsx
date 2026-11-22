import React, { useCallback, useEffect, useState } from 'react';
import { Upload } from 'lucide-react';
import { api, errorMessage } from '@/lib/api-client';
import { formatDate, titleCase } from '@/lib/format';
import type { Agency, ImportResult, LicenseHistory } from '@/types/models';
import { useAdminAuth } from '@/app/providers/AuthProvider';
import { Button } from '@/components/ui/Button';
import { DataTable, type Column } from '@/components/ui/DataTable';
import { Input, Select } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { ErrorState, LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { Pagination } from '@/components/ui/Pagination';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';

const statusOptions = [
  { value: '', label: 'All license statuses' },
  { value: 'active', label: 'Active' },
  { value: 'suspended', label: 'Suspended' },
  { value: 'expired', label: 'Expired' },
  { value: 'cancelled', label: 'Cancelled' },
  { value: 'unknown', label: 'Unknown' },
];

const editStatusOptions = statusOptions.filter((option) => option.value);

export const AgenciesPage: React.FC = () => {
  const { user } = useAdminAuth();
  const { push } = useToast();
  const [rows, setRows] = useState<Agency[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [district, setDistrict] = useState('');
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selected, setSelected] = useState<Agency | null>(null);
  const [licenses, setLicenses] = useState<LicenseHistory[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editStatus, setEditStatus] = useState('active');
  const [editLicense, setEditLicense] = useState('');
  const [editExpiry, setEditExpiry] = useState('');
  const [saving, setSaving] = useState(false);

  const [importOpen, setImportOpen] = useState(false);
  const [snapshotDate, setSnapshotDate] = useState('');
  const [dryRun, setDryRun] = useState(true);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.page<Agency>('/agencies', {
        page,
        page_size: 20,
        q: search,
        status,
        district,
        sort: 'name',
        order: 'asc',
      });
      setRows(result.items);
      setTotal(result.meta.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, status, district, search]);

  useEffect(() => {
    void load();
  }, [load]);

  const openAgency = async (agency: Agency) => {
    setSelected(agency);
    setEditStatus(agency.license_status);
    setEditLicense(agency.license_no ?? '');
    setEditExpiry(agency.license_expires_on ?? '');
    setDetailLoading(true);
    setLicenses([]);
    try {
      setLicenses(await api.get<LicenseHistory[]>(`/agencies/${agency.id}/licenses`));
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setDetailLoading(false);
    }
  };

  const saveAgency = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      const updated = await api.patch<Agency>(`/agencies/${selected.id}`, {
        license_status: editStatus,
        license_no: editLicense || null,
        license_expires_on: editExpiry || null,
      });
      setSelected(updated);
      push('Agency updated');
      await load();
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setSaving(false);
    }
  };

  const runImport = async (event: React.FormEvent) => {
    event.preventDefault();
    setImporting(true);
    setImportResult(null);
    try {
      const result = await api.post<ImportResult>('/agencies/import', {
        snapshot_date: snapshotDate || null,
        dry_run: dryRun,
      });
      setImportResult(result);
      push(result.dry_run ? 'Dry run complete' : 'Import complete');
      if (!result.dry_run) await load();
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setImporting(false);
    }
  };

  const columns: Column<Agency>[] = [
    {
      key: 'name',
      header: 'Agency',
      render: (row) => (
        <div className="cell-stack">
          <strong>{row.name}</strong>
          <span className="muted">{row.registration_no}</span>
        </div>
      ),
    },
    { key: 'district', header: 'District', render: (row) => row.district ?? '—' },
    { key: 'license_no', header: 'License', render: (row) => row.license_no ?? '—' },
    {
      key: 'license_status',
      header: 'License status',
      render: (row) => <StatusBadge status={row.license_status} />,
    },
    {
      key: 'license_expires_on',
      header: 'Expires',
      render: (row) => (row.license_expires_on ? formatDate(row.license_expires_on) : '—'),
    },
  ];

  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <h1>Agencies</h1>
          <p>SLBFE registrations, license status and import history.</p>
        </div>
        {user?.role === 'admin' && (
          <Button onClick={() => setImportOpen(true)}>
            <Upload size={16} /> Import SLBFE data
          </Button>
        )}
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
            label="Search name"
            name="q"
            value={query}
            placeholder="Agency name or registration"
            onChange={(event) => setQuery(event.target.value)}
          />
          <Select
            label="License status"
            name="status"
            value={status}
            options={statusOptions}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          />
          <Input
            label="District"
            name="district"
            value={district}
            onChange={(event) => {
              setDistrict(event.target.value);
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
                setDistrict('');
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
            emptyMessage="No agencies match these filters."
            onRowClick={openAgency}
          />
          <Pagination page={page} pageSize={20} total={total} onPageChange={setPage} />
        </>
      )}

      <Modal
        open={Boolean(selected)}
        title={selected?.name ?? 'Agency'}
        onClose={() => setSelected(null)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setSelected(null)}>Close</Button>
            {user?.role === 'admin' && (
              <Button onClick={saveAgency} loading={saving}>Save</Button>
            )}
          </>
        }
      >
        {selected && (
          <div className="stack-sm">
            <div className="detail-grid">
              <div><span>Registration</span><strong>{selected.registration_no}</strong></div>
              <div><span>District</span><strong>{selected.district ?? '—'}</strong></div>
              <div><span>Phone</span><strong>{selected.phone ?? '—'}</strong></div>
              <div><span>Email</span><strong>{selected.email ?? '—'}</strong></div>
            </div>
            {user?.role === 'admin' ? (
              <div className="form-row">
                <Select
                  label="License status"
                  name="edit_status"
                  value={editStatus}
                  options={editStatusOptions}
                  onChange={(event) => setEditStatus(event.target.value)}
                />
                <Input
                  label="License number"
                  name="edit_license"
                  value={editLicense}
                  onChange={(event) => setEditLicense(event.target.value)}
                />
                <Input
                  label="Expires on"
                  name="edit_expiry"
                  type="date"
                  value={editExpiry}
                  onChange={(event) => setEditExpiry(event.target.value)}
                />
              </div>
            ) : (
              <div className="detail-grid">
                <div><span>License</span><strong>{selected.license_no ?? '—'}</strong></div>
                <div><span>Status</span><strong>{titleCase(selected.license_status)}</strong></div>
                <div><span>Expires</span><strong>{formatDate(selected.license_expires_on)}</strong></div>
              </div>
            )}
            <h3>License history</h3>
            {detailLoading ? (
              <LoadingSpinner label="Loading licenses…" />
            ) : licenses.length === 0 ? (
              <p className="muted">No license history recorded.</p>
            ) : (
              <ul className="timeline">
                {licenses.map((license) => (
                  <li key={license.id}>
                    <span className="timeline-dot" />
                    <div>
                      <strong>{license.license_no ?? 'No license number'}</strong>
                      <span className="muted">
                        <StatusBadge status={license.status} /> issued {formatDate(license.issued_on)} · expires {formatDate(license.expires_on)}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </Modal>

      <Modal
        open={importOpen}
        title="Import SLBFE agencies"
        onClose={() => setImportOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setImportOpen(false)}>Close</Button>
            <Button onClick={runImport} loading={importing} disabled={false}>
              {dryRun ? 'Run dry run' : 'Import now'}
            </Button>
          </>
        }
      >
        <form className="stack-sm" onSubmit={runImport}>
          <p className="muted">Imports from the server-configured SLBFE source.</p>
          <Input
            label="Snapshot date"
            name="snapshot_date"
            type="date"
            value={snapshotDate}
            onChange={(event) => setSnapshotDate(event.target.value)}
          />
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(event) => setDryRun(event.target.checked)}
            />
            Dry run (parse only, no writes)
          </label>
          {importResult && (
            <div className={importResult.errors.length ? 'form-error' : 'form-success'}>
              Parsed {importResult.parsed}, imported {importResult.imported}.{' '}
              {importResult.duplicate_snapshot && 'Duplicate snapshot: nothing changed. '}
              {importResult.errors.length > 0 && `${importResult.errors.length} row error(s).`}
            </div>
          )}
        </form>
      </Modal>
    </div>
  );
};
