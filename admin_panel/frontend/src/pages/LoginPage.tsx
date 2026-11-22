import { type FormEvent, useEffect, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import { DEMO_PASSWORD } from '../api/mock/seed.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import { Icon, Logo } from '../components/icons.tsx';

const MAX_ATTEMPTS = 5;
const LOCK_SECONDS = 30;

const DEMO_ACCOUNTS = [
  { email: 'admin@prawdowid.demo', role: 'Administrator', note: 'pełny dostęp, konfiguracja modeli' },
  { email: 'analityk@prawdowid.demo', role: 'Analityk', note: 'luki informacyjne, źródła' },
  { email: 'moderator@prawdowid.demo', role: 'Moderator', note: 'alerty i sprawy' },
];

export default function LoginPage() {
  const { user, login, notice } = useAuth();
  const api = getApi();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? '/';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failures, setFailures] = useState(0);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [capsLock, setCapsLock] = useState(false);

  useEffect(() => {
    if (!lockedUntil) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= lockedUntil) {
        setLockedUntil(null);
        setFailures(0);
      }
    }, 500);
    return () => window.clearInterval(timer);
  }, [lockedUntil]);

  if (user) return <Navigate to={from} replace />;

  // backend/admin has no accounts: one shared token plus a name for the audit log.
  const tokenLogin = api.mode === 'http';
  const locked = lockedUntil !== null && now < lockedUntil;
  const secondsLeft = locked ? Math.ceil((lockedUntil - now) / 1000) : 0;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (locked || busy) return;
    if (!email.trim() || !password) {
      setError(tokenLogin ? 'Podaj imię i nazwisko oraz token administratora.' : 'Podaj adres e-mail i hasło.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      const next = failures + 1;
      setFailures(next);
      setPassword('');
      if (next >= MAX_ATTEMPTS) {
        setLockedUntil(Date.now() + LOCK_SECONDS * 1000);
        setNow(Date.now());
        setError(`Zbyt wiele nieudanych prób. Logowanie zablokowane na ${LOCK_SECONDS} s.`);
      } else {
        setError((err as Error).message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-brand">
          <Logo size={44} />
          <div>
            <h1>Prawdowid</h1>
            <p>Panel administracyjny weryfikacji informacji</p>
          </div>
        </div>

        {notice && (
          <div className="notice notice-info" role="status">
            <Icon name="info" size={16} />
            {notice}
          </div>
        )}

        <form className="login-form" onSubmit={submit} noValidate>
          <label className="field">
            <span className="field-label">{tokenLogin ? 'Imię i nazwisko' : 'Adres e-mail'}</span>
            <input
              type={tokenLogin ? 'text' : 'email'}
              autoComplete={tokenLogin ? 'name' : 'username'}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={locked}
              required
              autoFocus
            />
          </label>
          {tokenLogin && (
            <span className="field-hint login-hint">Trafia do dziennika audytu przy każdej zmianie konfiguracji.</span>
          )}
          <label className="field">
            <span className="field-label">{tokenLogin ? 'Token administratora' : 'Hasło'}</span>
            <div className="input-with-btn">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyUp={(e) => setCapsLock(e.getModifierState('CapsLock'))}
                disabled={locked}
                required
              />
              <button
                type="button"
                className="icon-btn"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? (tokenLogin ? 'Ukryj token' : 'Ukryj hasło') : tokenLogin ? 'Pokaż token' : 'Pokaż hasło'}
              >
                <Icon name={showPassword ? 'eyeOff' : 'eye'} size={18} />
              </button>
            </div>
            {capsLock && <span className="field-hint">Włączony Caps Lock.</span>}
            {tokenLogin && !capsLock && (
              <span className="field-hint">
                Wartość <code>ADMIN_API_TOKEN</code> ustawiona w backendzie panelu.
              </span>
            )}
          </label>

          {error && (
            <div className="notice notice-critical" role="alert">
              <Icon name="alert" size={16} />
              <div>
                {error}
                {tokenLogin && /połączenia|503|wyłączony/i.test(error) && (
                  <div className="small login-help">
                    Uruchom backend: <code>cd backend</code>, potem{' '}
                    <code>ADMIN_API_TOKEN=&lt;token&gt; uvicorn admin.api:create_app --factory --port 8100</code>. Bez
                    backendu: <code>npm run dev:demo</code> (dane przykładowe).
                  </div>
                )}
              </div>
            </div>
          )}

          <button type="submit" className="btn btn-primary btn-block" disabled={busy || locked}>
            {busy ? 'Logowanie…' : locked ? `Spróbuj za ${secondsLeft} s` : 'Zaloguj się'}
          </button>
          {failures > 0 && !locked && (
            <p className="muted small">
              Nieudane próby: {failures} z {MAX_ATTEMPTS}. Po przekroczeniu limitu logowanie zostanie czasowo
              zablokowane.
            </p>
          )}
        </form>

        {api.mode === 'mock' && (
          <div className="demo-accounts">
            <div className="demo-accounts-head">
              <Icon name="info" size={16} />
              <strong>Tryb demonstracyjny</strong> — konta przykładowe, hasło: <code>{DEMO_PASSWORD}</code>
            </div>
            <ul>
              {DEMO_ACCOUNTS.map((a) => (
                <li key={a.email}>
                  <button
                    type="button"
                    className="demo-account"
                    onClick={() => {
                      setEmail(a.email);
                      setPassword(DEMO_PASSWORD);
                      setError(null);
                    }}
                  >
                    <span>
                      <strong>{a.role}</strong>
                      <span className="muted"> · {a.note}</span>
                    </span>
                    <span className="mono small">{a.email}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="login-foot">
          <Icon name="lock" size={14} /> Dostęp wyłącznie dla upoważnionych osób. Logowania i działania w panelu są
          zapisywane w dzienniku audytu.
          {api.mode === 'http' && (
            <>
              {' '}
              API: <code>{api.target}</code>
            </>
          )}
        </p>
      </div>
    </div>
  );
}
