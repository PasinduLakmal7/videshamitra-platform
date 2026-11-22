import React from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { useAdminAuth } from '@/app/providers/AuthProvider';
import { Button } from '@/components/ui/Button';

export const Header: React.FC = () => {
  const { user, logout } = useAdminAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className="topbar">
      <div>
        <h1 className="topbar-title">Migration safety operations</h1>
        <p className="topbar-subtitle">Case review, evidence and worker protection</p>
      </div>
      <div className="topbar-user">
        <div className="avatar">{(user?.full_name ?? 'U').slice(0, 1).toUpperCase()}</div>
        <div className="topbar-identity">
          <strong>{user?.full_name ?? 'Unknown user'}</strong>
          <span>{user?.email ?? user?.phone ?? ''}</span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleLogout} aria-label="Sign out">
          <LogOut size={16} />
          Sign out
        </Button>
      </div>
    </header>
  );
};
