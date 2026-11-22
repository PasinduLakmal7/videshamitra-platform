import React from 'react';
import { Link } from 'react-router-dom';

export const ForbiddenPage: React.FC = () => (
  <div className="centered-screen">
    <div className="empty-state">
      <h1>403 — Staff only</h1>
      <p>Your account does not have permission to view this page.</p>
      <Link className="btn btn-primary btn-md" to="/">Back to dashboard</Link>
    </div>
  </div>
);

export const NotFoundPage: React.FC = () => (
  <div className="centered-screen">
    <div className="empty-state">
      <h1>404 — Not found</h1>
      <p>The page you requested does not exist.</p>
      <Link className="btn btn-primary btn-md" to="/">Back to dashboard</Link>
    </div>
  </div>
);
