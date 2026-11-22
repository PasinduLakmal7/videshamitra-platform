import React from 'react';
import { Link, useLocation } from 'react-router-dom';

const LABELS: Record<string, string> = {
  cases: 'Cases',
  agencies: 'Agencies',
  users: 'Users',
  audit: 'Audit log',
  admin: 'Admin',
};

export const Breadcrumbs: React.FC = () => {
  const location = useLocation();
  const parts = location.pathname.split('/').filter(Boolean);
  if (parts.length === 0) return null;
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <Link to="/">Dashboard</Link>
      {parts.map((part, index) => {
        const path = '/' + parts.slice(0, index + 1).join('/');
        const label = LABELS[part] ?? (part.length > 12 ? `#${part.slice(0, 8)}` : part);
        const last = index === parts.length - 1;
        return (
          <span key={path}>
            <span className="crumb-sep">/</span>
            {last ? <span>{label}</span> : <Link to={path}>{label}</Link>}
          </span>
        );
      })}
    </nav>
  );
};
