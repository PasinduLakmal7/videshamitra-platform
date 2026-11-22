import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  BriefcaseBusiness,
  FolderKanban,
  MapPinned,
  ShieldAlert,
  Users,
} from 'lucide-react';
import { api, errorMessage } from '@/lib/api-client';
import { formatDate, titleCase } from '@/lib/format';
import type { Dashboard } from '@/types/models';
import { EmptyState, ErrorState, LoadingSpinner } from '@/components/ui/LoadingSpinner';
import { StatusBadge } from '@/components/ui/StatusBadge';

const metricCards = [
  { key: 'workers', label: 'Active workers', icon: Users, tone: 'blue' },
  { key: 'active_journeys', label: 'Active journeys', icon: MapPinned, tone: 'teal' },
  { key: 'verifications_this_week', label: 'Verifications / week', icon: BriefcaseBusiness, tone: 'purple' },
  { key: 'high_risk_verifications', label: 'High-risk (30d)', icon: ShieldAlert, tone: 'red' },
  { key: 'open_cases', label: 'Open cases', icon: FolderKanban, tone: 'amber' },
  { key: 'overdue_checkins', label: 'Overdue check-ins', icon: AlertTriangle, tone: 'red' },
] as const;

export const AdminDashboardPage: React.FC = () => {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await api.get<Dashboard>('/admin/dashboard'));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <LoadingSpinner label="Loading dashboard…" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <EmptyState title="No dashboard data" />;

  return (
    <div className="stack">
      <div className="page-heading">
        <div>
          <h1>Dashboard</h1>
          <p>Live operational picture across workers, verifications and cases.</p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
          Refresh
        </button>
      </div>

      <div className="metric-grid">
        {metricCards.map((card) => {
          const Icon = card.icon;
          return (
            <div key={card.key} className={`metric-card tone-${card.tone}`}>
              <span className="metric-icon">
                <Icon size={20} />
              </span>
              <span className="metric-value">{data.metrics[card.key]}</span>
              <span className="metric-label">{card.label}</span>
            </div>
          );
        })}
      </div>

      <div className="dashboard-grid">
        <section className="card">
          <div className="card-header">
            <h2>Recent activity</h2>
          </div>
          {data.recent_activity.length === 0 ? (
            <EmptyState title="No recent activity" />
          ) : (
            <ul className="activity-list">
              {data.recent_activity.map((item) => (
                <li key={`${item.kind}-${item.id}`}>
                  <span className={`activity-dot ${item.kind}`} />
                  <div className="activity-body">
                    <strong>{item.title}</strong>
                    <span>
                      {titleCase(item.kind)} · {formatDate(item.created_at)}
                    </span>
                  </div>
                  <StatusBadge status={item.status} />
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card">
          <div className="card-header">
            <h2>Open cases by tier</h2>
          </div>
          {data.metrics.open_cases_by_tier.length === 0 ? (
            <EmptyState title="No open cases" />
          ) : (
            <div className="tier-list">
              {data.metrics.open_cases_by_tier.map((tier) => (
                <div key={tier.tier} className="tier-row">
                  <span className={`tier-chip tier-${tier.tier}`}>Tier {tier.tier}</span>
                  <div className="tier-bar">
                    <span
                      style={{
                        width: `${Math.min(
                          100,
                          (tier.count /
                            Math.max(1, ...data.metrics.open_cases_by_tier.map((item) => item.count))) *
                            100,
                        )}%`,
                      }}
                    />
                  </div>
                  <strong>{tier.count}</strong>
                </div>
              ))}
            </div>
          )}
          <div className="alert-row">
            <span>Agency license alerts</span>
            <strong>{data.metrics.agency_alerts}</strong>
          </div>
        </section>
      </div>
    </div>
  );
};
