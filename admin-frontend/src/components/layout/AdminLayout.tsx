import React from 'react';
import { Outlet } from 'react-router-dom';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { Breadcrumbs } from './Breadcrumbs';

export const AdminLayout: React.FC = () => (
  <div className="app-shell">
    <Sidebar />
    <div className="app-main">
      <Header />
      <main className="page">
        <Breadcrumbs />
        <Outlet />
      </main>
    </div>
  </div>
);
