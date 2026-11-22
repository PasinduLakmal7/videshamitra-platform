import React from 'react';

const COLORS: Record<string, string> = {
  active: 'green',
  verified: 'green',
  low: 'green',
  completed: 'green',
  resolved: 'green',
  closed: 'gray',
  suspended: 'red',
  fraudulent: 'red',
  critical: 'red',
  high: 'red',
  missed: 'red',
  expired: 'amber',
  unknown: 'amber',
  suspicious: 'amber',
  medium: 'amber',
  submitted: 'blue',
  under_review: 'blue',
  scheduled: 'blue',
  sent: 'blue',
  escalated: 'purple',
  processing: 'purple',
  draft: 'gray',
  cancelled: 'gray',
  failed: 'gray',
};

export const StatusBadge: React.FC<{ status?: string | null; label?: string }> = ({
  status,
  label,
}) => {
  const key = (status ?? 'unknown').toLowerCase();
  const color = COLORS[key] ?? 'gray';
  return <span className={`badge badge-${color}`}>{label ?? (status ?? 'unknown').replace(/_/g, ' ')}</span>;
};
