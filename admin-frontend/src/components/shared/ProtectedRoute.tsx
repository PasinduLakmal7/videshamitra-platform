import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAdminAuth } from '@/app/providers/AuthProvider';
import { LoadingSpinner } from '@/components/ui/LoadingSpinner';
import type { Role } from '@/types/models';

interface ProtectedRouteProps {
  children: React.ReactNode;
  roles?: Role[];
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, roles }) => {
  const { user, loading } = useAdminAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="centered-screen">
        <LoadingSpinner label="Checking your session…" />
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to="/403" replace />;
  }
  return <>{children}</>;
};

export const RoleGuard: React.FC<{ roles: Role[]; children: React.ReactNode }> = ({
  roles,
  children,
}) => {
  const { user } = useAdminAuth();
  if (!user || !roles.includes(user.role)) {
    return <div className="error-state">You do not have permission to view this page.</div>;
  }
  return <>{children}</>;
};
