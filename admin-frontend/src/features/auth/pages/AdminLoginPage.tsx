import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAdminAuth } from '@/app/providers/AuthProvider';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { errorMessage } from '@/lib/api-client';

export const AdminLoginPage: React.FC = () => {
  const { user, login } = useAdminAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) navigate('/', { replace: true });
  }, [user, navigate]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate('/', { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-panel">
        <div className="login-brand">
          <span className="login-mark">VM</span>
          <div>
            <h1>VideshaMitra</h1>
            <p>Caseworker &amp; administrator portal</p>
          </div>
        </div>
        <form onSubmit={submit} className="login-form">
          <Input
            label="Email"
            name="email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="caseworker@videshamitra.lk"
          />
          <Input
            label="Password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="••••••••"
          />
          {error && <div className="form-error" role="alert">{error}</div>}
          <Button type="submit" fullWidth loading={busy}>
            Sign in
          </Button>
        </form>
        <p className="login-hint">
          Worker accounts cannot sign in here. Staff access is limited to
          caseworker and administrator roles.
        </p>
      </div>
    </div>
  );
};
