import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, ApiError, clearSession, getSession, setSession } from '@/lib/api-client';
import type { Session, SessionUser } from '@/types/models';

interface AuthContextValue {
  user: SessionUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AdminAuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<SessionUser | null>(getSession()?.user ?? null);
  const [loading, setLoading] = useState<boolean>(Boolean(getSession()));

  useEffect(() => {
    const onCleared = () => setUser(null);
    window.addEventListener('vm:session-cleared', onCleared);
    return () => window.removeEventListener('vm:session-cleared', onCleared);
  }, []);

  useEffect(() => {
    if (!getSession()) return;
    let active = true;
    api
      .get<SessionUser>('/auth/me')
      .then((profile) => {
        if (!active) return;
        if (profile.role === 'worker') {
          clearSession();
          setUser(null);
          return;
        }
        setUser(profile);
        const session = getSession();
        if (session) setSession({ ...session, user: profile });
      })
      .catch((err) => {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) clearSession();
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.post<Session>('/auth/login', { email, password });
    if (session.user.role === 'worker') {
      throw new ApiError(403, 'forbidden', 'Worker accounts cannot access the admin portal');
    }
    setSession(session);
    setUser(session.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Local logout must still succeed if the token already expired.
    }
    clearSession();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
};

export function useAdminAuth(): AuthContextValue {
  const context = useContext(AdminAuthContext);
  if (!context) throw new Error('useAdminAuth must be used inside AuthProvider');
  return context;
}
