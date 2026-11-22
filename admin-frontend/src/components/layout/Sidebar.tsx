import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Building2,
  FolderKanban,
  LayoutDashboard,
  ScrollText,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { useAdminAuth } from '@/app/providers/AuthProvider';

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/cases', label: 'Cases', icon: FolderKanban },
  { to: '/agencies', label: 'Agencies', icon: Building2 },
  { to: '/users', label: 'Users', icon: Users, adminOnly: true },
  { to: '/audit', label: 'Audit log', icon: ScrollText, adminOnly: true },
];

export const Sidebar: React.FC = () => {
  const { user } = useAdminAuth();
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">
          <ShieldCheck size={22} />
        </span>
        <div>
          <strong>VideshaMitra</strong>
          <span>Caseworker console</span>
        </div>
      </div>
      <nav className="sidebar-nav">
        {links
          .filter((link) => !link.adminOnly || user?.role === 'admin')
          .map((link) => {
            const Icon = link.icon;
            return (
              <NavLink
                key={link.to}
                to={link.to}
                end={link.end}
                className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
              >
                <Icon size={18} />
                <span>{link.label}</span>
              </NavLink>
            );
          })}
      </nav>
      <div className="sidebar-footer">
        <span className={`role-pill role-${user?.role}`}>{user?.role ?? 'guest'}</span>
        <span className="sidebar-note">core-api v1</span>
      </div>
    </aside>
  );
};
