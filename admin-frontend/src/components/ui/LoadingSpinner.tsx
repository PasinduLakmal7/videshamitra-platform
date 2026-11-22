import React from 'react';

export const LoadingSpinner: React.FC<{ label?: string }> = ({ label = 'Loading…' }) => (
  <div className="spinner-wrap" role="status">
    <span className="spinner" aria-hidden="true" />
    <span>{label}</span>
  </div>
);

export const EmptyState: React.FC<{ title: string; description?: string }> = ({
  title,
  description,
}) => (
  <div className="empty-state">
    <h3>{title}</h3>
    {description && <p>{description}</p>}
  </div>
);

export const ErrorState: React.FC<{ message: string; onRetry?: () => void }> = ({
  message,
  onRetry,
}) => (
  <div className="error-state" role="alert">
    <p>{message}</p>
    {onRetry && (
      <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
        Retry
      </button>
    )}
  </div>
);
