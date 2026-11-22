import { createBrowserRouter } from 'react-router-dom';
import { AdminLayout } from '@/components/layout/AdminLayout';
import { ProtectedRoute } from '@/components/shared/ProtectedRoute';
import { AdminLoginPage } from '@/features/auth/pages/AdminLoginPage';
import { AdminDashboardPage } from '@/features/dashboard/pages/AdminDashboardPage';
import { CasesPage } from '@/features/case-management/pages/CasesPage';
import { CaseDetailsPage } from '@/features/case-management/pages/CaseDetailsPage';
import { AgenciesPage } from '@/features/agencies/pages/AgenciesPage';
import { UsersPage } from '@/features/users/pages/UsersPage';
import { AuditPage } from '@/features/audit/pages/AuditPage';
import { ForbiddenPage, NotFoundPage } from '@/features/system/pages/SystemPages';

export const router = createBrowserRouter([
  { path: '/login', element: <AdminLoginPage /> },
  {
    path: '/',
    element: (
      <ProtectedRoute>
        <AdminLayout />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <AdminDashboardPage /> },
      { path: 'cases', element: <CasesPage /> },
      { path: 'cases/:caseId', element: <CaseDetailsPage /> },
      { path: 'agencies', element: <AgenciesPage /> },
      {
        path: 'users',
        element: (
          <ProtectedRoute roles={['admin']}>
            <UsersPage />
          </ProtectedRoute>
        ),
      },
      {
        path: 'audit',
        element: (
          <ProtectedRoute roles={['admin']}>
            <AuditPage />
          </ProtectedRoute>
        ),
      },
      { path: '403', element: <ForbiddenPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
