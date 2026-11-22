import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Download, FileSearch, StickyNote } from 'lucide-react';
import { api, errorMessage } from '@/lib/api-client';
import { formatBytes, formatDate, titleCase } from '@/lib/format';
import type { CaseDetail, User } from '@/types/models';
import { Button } from '@/components/ui/Button';
import { Select, Textarea } from '@/components/ui/Input';
import { Modal } from '@/components/ui/Modal';
import { ErrorState, LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { useToast } from '@/components/ui/Toast';
import { useAdminAuth } from '@/app/providers/AuthProvider';

const statusOptions = [
  { value: 'draft', label: 'Draft (worker-owned)' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'under_review', label: 'Under review' },
  { value: 'escalated', label: 'Escalated' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'closed', label: 'Closed' },
];

const tierOptions = [
  { value: '1', label: 'Tier 1' },
  { value: '2', label: 'Tier 2' },
  { value: '3', label: 'Tier 3' },
];

export const CaseDetailsPage: React.FC = () => {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const { push } = useToast();
  const { user } = useAdminAuth();

  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [staff, setStaff] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [tier, setTier] = useState('1');
  const [assignee, setAssignee] = useState('');
  const [note, setNote] = useState('');
  const [escalationReason, setEscalationReason] = useState('');
  const [escalateOpen, setEscalateOpen] = useState(false);
  const [trace, setTrace] = useState<unknown>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);

  const load = useCallback(async () => {
    if (!caseId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.get<CaseDetail>(`/admin/cases/${caseId}`);
      setDetail(data);
      setStatus(data.case.status);
      setTier(String(data.case.triage_tier));
      setAssignee(data.case.assigned_to ?? '');
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api
      .page<User>('/users', { role: 'caseworker', page_size: 100 })
      .then((result) => setStaff(result.items))
      .catch(() => setStaff([]));
    if (user?.role === 'admin') {
      api
        .page<User>('/users', { role: 'admin', page_size: 100 })
        .then((result) => setStaff((current) => [...current, ...result.items]))
        .catch(() => undefined);
    }
  }, [user?.role]);

  const assigneeOptions = useMemo(
    () => [
      { value: '', label: 'Unassigned' },
      ...staff.map((member) => ({
        value: member.id,
        label: member.full_name ? `${member.full_name} (${member.role})` : member.id,
      })),
    ],
    [staff],
  );

  const saveStatus = async () => {
    if (!caseId) return;
    setBusy(true);
    try {
      await api.patch(`/admin/cases/${caseId}`, {
        status,
        triage_tier: Number(tier),
        assigned_to: assignee || null,
      });
      push('Case updated');
      await load();
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const addNote = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!caseId || !note.trim()) return;
    setBusy(true);
    try {
      await api.post(`/admin/cases/${caseId}/notes`, { body: note.trim() });
      setNote('');
      push('Note added');
      await load();
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const escalate = async () => {
    if (!caseId) return;
    setBusy(true);
    try {
      await api.post(`/admin/cases/${caseId}/escalate`, {
        reason: escalationReason || undefined,
        triage_tier: Number(tier),
      });
      setEscalateOpen(false);
      setEscalationReason('');
      push('Case escalated');
      await load();
    } catch (err) {
      push(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const loadTrace = async () => {
    if (!detail?.verification) return;
    setTraceLoading(true);
    setTraceError(null);
    try {
      setTrace(await api.get(`/admin/verifications/${detail.verification.id}/trace`));
    } catch (err) {
      setTraceError(errorMessage(err));
    } finally {
      setTraceLoading(false);
    }
  };

  const download = async (documentId: string) => {
    try {
      const result = await api.get<{ url: string; expires_in: number }>(
        `/documents/${documentId}/download-url`,
      );
      window.open(result.url, '_blank', 'noopener,noreferrer');
    } catch (err) {
      push(errorMessage(err), 'error');
    }
  };

  if (loading) return <LoadingSpinner label="Loading case…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!detail) return <ErrorState message="Case not found" />;

  const { case: complaint, worker, journey, verification, checkin, documents, notes } = detail;

  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <button type="button" className="back-link" onClick={() => navigate('/cases')}>
            <ArrowLeft size={16} /> Back to case queue
          </button>
          <h1>{complaint.title}</h1>
          <p>
            Case #{complaint.id.slice(0, 8)} · opened {formatDate(complaint.created_at)}
          </p>
        </div>
        <Button variant="danger" onClick={() => setEscalateOpen(true)}>
          Escalate case
        </Button>
      </div>

      <div className="case-grid">
        <div className="stack">
          <section className="card">
            <div className="card-header">
              <h2>Overview</h2>
              <StatusBadge status={complaint.status} />
            </div>
            <div className="detail-grid">
              <div><span>Worker</span><strong>{worker?.full_name ?? complaint.worker_name ?? '—'}</strong></div>
              <div><span>Phone</span><strong>{worker?.phone ?? complaint.worker_phone ?? '—'}</strong></div>
              <div><span>Agency</span><strong>{complaint.agency_name ?? '—'}</strong></div>
              <div><span>Tier</span><strong>T{complaint.triage_tier}</strong></div>
              <div><span>Submitted</span><strong>{formatDate(complaint.submitted_at)}</strong></div>
              <div><span>Assigned</span><strong>{staff.find((item) => item.id === complaint.assigned_to)?.full_name ?? 'Unassigned'}</strong></div>
            </div>
            {complaint.description && <p className="paragraph">{complaint.description}</p>}
            {journey && (
              <div className="sub-panel">
                <h3>Journey</h3>
                <div className="detail-grid">
                  <div><span>Stage</span><strong>{titleCase(journey.stage)}</strong></div>
                  <div><span>Destination</span><strong>{journey.destination_country ?? '—'}</strong></div>
                  <div><span>Employer</span><strong>{journey.employer_name ?? '—'}</strong></div>
                  <div><span>Next check-in</span><strong>{formatDate(journey.next_checkin_at)}</strong></div>
                </div>
              </div>
            )}
            {checkin && (
              <div className="sub-panel">
                <h3>Linked check-in</h3>
                <div className="detail-grid">
                  <div><span>Due</span><strong>{formatDate(checkin.due_at)}</strong></div>
                  <div><span>Status</span><strong>{titleCase(checkin.status)}</strong></div>
                  <div><span>Risk</span><strong>{checkin.risk_level ?? '—'}</strong></div>
                </div>
              </div>
            )}
          </section>

          {verification && (
            <section className="card">
              <div className="card-header">
                <h2>Verification</h2>
                <StatusBadge status={verification.status} />
              </div>
              <div className="detail-grid">
                <div><span>Job</span><strong>{verification.job_title ?? '—'}</strong></div>
                <div><span>Employer</span><strong>{verification.employer_name ?? '—'}</strong></div>
                <div><span>Risk</span><strong>{verification.risk_level ?? '—'} {verification.risk_score != null ? `(${verification.risk_score})` : ''}</strong></div>
                <div><span>Engine</span><strong>{verification.engine_version ?? '—'}</strong></div>
              </div>
              {verification.findings && verification.findings.length > 0 && (
                <ul className="finding-list">
                  {verification.findings.map((finding, index) => (
                    <li key={`${finding.code ?? 'finding'}-${index}`}>
                      <strong>{finding.code?.replace(/_/g, ' ') ?? 'Finding'}</strong>
                      <span>{finding.message}</span>
                      {finding.source && <em>{finding.source}</em>}
                    </li>
                  ))}
                </ul>
              )}
              <div className="button-row">
                <Button variant="secondary" size="sm" onClick={loadTrace} loading={traceLoading}>
                  <FileSearch size={16} /> View AI trace
                </Button>
              </div>
              {traceError && <div className="form-error">{traceError}</div>}
            </section>
          )}

          <section className="card">
            <div className="card-header">
              <h2>Evidence</h2>
              <span className="muted">{documents.length} document(s)</span>
            </div>
            {documents.length === 0 ? (
              <p className="muted">No documents attached.</p>
            ) : (
              <ul className="document-list">
                {documents.map((document) => (
                  <li key={document.id}>
                    <div>
                      <strong>{document.original_filename}</strong>
                      <span className="muted">
                        {titleCase(document.type)} · {formatBytes(document.size_bytes)} · {formatDate(document.created_at)}
                      </span>
                    </div>
                    <Button variant="secondary" size="sm" onClick={() => download(document.id)}>
                      <Download size={15} /> Download
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <div className="card-header">
              <h2>Case notes</h2>
              <span className="muted">{notes.length} note(s)</span>
            </div>
            {notes.length === 0 ? (
              <p className="muted">No notes yet.</p>
            ) : (
              <ul className="note-list">
                {notes.map((item) => (
                  <li key={item.id}>
                    <div className="note-head">
                      <strong>{item.author_name ?? 'System'}</strong>
                      <span>{formatDate(item.created_at)}</span>
                    </div>
                    <p>{item.body}</p>
                  </li>
                ))}
              </ul>
            )}
            <form onSubmit={addNote} className="note-form">
              <Textarea
                label="Add note"
                name="note"
                rows={3}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Record your review, evidence check or next action…"
              />
              <Button type="submit" size="sm" loading={busy} disabled={!note.trim()}>
                <StickyNote size={16} /> Add note
              </Button>
            </form>
          </section>
        </div>

        <aside className="stack">
          <section className="card">
            <div className="card-header"><h2>Actions</h2></div>
            <div className="stack-sm">
              <Select
                label="Status"
                name="status"
                options={statusOptions}
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              />
              <Select
                label="Tier"
                name="tier"
                options={tierOptions}
                value={tier}
                onChange={(event) => setTier(event.target.value)}
              />
              <Select
                label="Assignee"
                name="assignee"
                options={assigneeOptions}
                value={assignee}
                onChange={(event) => setAssignee(event.target.value)}
              />
              <Button onClick={saveStatus} loading={busy}>Save changes</Button>
            </div>
          </section>
          <section className="card">
            <div className="card-header"><h2>Raw evidence</h2></div>
            <pre className="json-block">{JSON.stringify(complaint.evidence ?? [], null, 2)}</pre>
          </section>
        </aside>
      </div>

      <Modal
        open={Boolean(trace)}
        title="AI analysis trace"
        onClose={() => setTrace(null)}
        footer={<Button variant="secondary" onClick={() => setTrace(null)}>Close</Button>}
      >
        <pre className="json-block">{JSON.stringify(trace, null, 2)}</pre>
      </Modal>

      <Modal
        open={escalateOpen}
        title="Escalate this case?"
        onClose={() => setEscalateOpen(false)}
        footer={
          <>
            <Button variant="secondary" onClick={() => setEscalateOpen(false)} disabled={busy}>
              Cancel
            </Button>
            <Button variant="danger" onClick={escalate} loading={busy}>
              Escalate case
            </Button>
          </>
        }
      >
        <p className="paragraph">
          Escalation notifies the worker and raises the case tier. This action is audited.
        </p>
        <Textarea
          label="Reason (optional)"
          name="escalation_reason"
          rows={3}
          value={escalationReason}
          onChange={(event) => setEscalationReason(event.target.value)}
          placeholder="Why is this being escalated?"
        />
      </Modal>
    </div>
  );
};
