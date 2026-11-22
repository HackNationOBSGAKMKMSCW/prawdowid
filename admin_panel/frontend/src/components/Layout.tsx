import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { getApi, supports } from '../api/index.ts';
import type { Feature } from '../api/types.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import type { Permission } from '../auth/permissions.ts';
import { getConfig } from '../config.ts';
import { Icon, type IconName, Logo } from './icons.tsx';
import { ROLE_LABEL } from './labels.ts';
import { Field, Modal, useAction } from './ui.tsx';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  permission: Permission;
  counter?: keyof Counts;
  /** Shown only when the data source supports this part of the panel. */
  feature?: Feature;
}

export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Przegląd',
    items: [
      { to: '/', label: 'Pulpit', icon: 'home', permission: 'dashboard:read' },
      { to: '/stats', label: 'Statystyki', icon: 'chart', permission: 'dashboard:read' },
    ],
  },
  {
    section: 'Monitoring',
    items: [
      { to: '/alerts', label: 'Alerty i ostrzeżenia', icon: 'bell', permission: 'alerts:read', counter: 'alerts' },
      { to: '/gaps', label: 'Luki informacyjne', icon: 'gap', permission: 'clusters:read', counter: 'gaps' },
      { to: '/repeated', label: 'Powtarzające się zapytania', icon: 'repeat', permission: 'clusters:read', feature: 'clusters' },
      { to: '/threats', label: 'Zagrożenia', icon: 'shield', permission: 'security:read', feature: 'threats' },
      { to: '/security', label: 'Bezpieczeństwo', icon: 'shield', permission: 'security:read', feature: 'securityEvents' },
      { to: '/end-users', label: 'Użytkownicy serwisu', icon: 'users', permission: 'endusers:read', feature: 'endUsers', counter: 'blocked' },
      { to: '/logs', label: 'Logi techniczne', icon: 'shield', permission: 'security:read', feature: 'techEvents' },
    ],
  },
  {
    section: 'Obsługa',
    items: [
      { to: '/cases', label: 'Sprawy moderatora', icon: 'folder', permission: 'cases:read', counter: 'cases', feature: 'cases' },
      { to: '/checks', label: 'Historia weryfikacji', icon: 'history', permission: 'checks:read' },
    ],
  },
  {
    section: 'Konfiguracja',
    items: [
      { to: '/sources', label: 'Katalog źródeł', icon: 'database', permission: 'sources:read', feature: 'sources' },
      { to: '/trusted-sites', label: 'Strony zaufane', icon: 'database', permission: 'sources:read', feature: 'trustedSites' },
      { to: '/models', label: 'Modele AI', icon: 'cpu', permission: 'models:read', feature: 'providers' },
      { to: '/runtime', label: 'Modele i źródła danych', icon: 'cpu', permission: 'models:read', feature: 'runtimeConfig' },
      { to: '/rules', label: 'Reguły alertów', icon: 'sliders', permission: 'rules:read', feature: 'alertRules' },
      { to: '/thresholds', label: 'Reguły i progi', icon: 'sliders', permission: 'settings:read', feature: 'runtimeConfig' },
      { to: '/settings', label: 'Kanały i prywatność', icon: 'settings', permission: 'settings:read', feature: 'channels' },
      { to: '/users', label: 'Użytkownicy', icon: 'users', permission: 'users:read', feature: 'staffUsers' },
      { to: '/audit', label: 'Dziennik audytu', icon: 'audit', permission: 'audit:read' },
    ],
  },
];

interface Counts {
  alerts: number;
  critical: number;
  gaps: number;
  cases: number;
  blocked: number;
}

const CountsContext = createContext<() => void>(() => {});

/** Pages call this after an action that changes alert/case counts. */
export function useRefreshCounts() {
  return useContext(CountsContext);
}

type Theme = 'light' | 'dark' | 'system';

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = localStorage.getItem('prawdowid-admin-theme');
      return saved === 'light' || saved === 'dark' ? saved : 'system';
    } catch {
      return 'system';
    }
  });
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', theme);
    try {
      localStorage.setItem('prawdowid-admin-theme', theme);
    } catch {
      // ignore
    }
  }, [theme]);
  const toggle = () => {
    const isDark =
      theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
    setTheme(isDark ? 'light' : 'dark');
  };
  return [theme, toggle];
}

export default function Layout() {
  const { user, logout, can } = useAuth();
  const api = getApi();
  const config = getConfig();
  const [menuOpen, setMenuOpen] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);
  const [counts, setCounts] = useState<Counts | null>(null);
  const [, toggleTheme] = useTheme();

  const refreshCounts = useCallback(() => {
    Promise.all([
      can('alerts:read') ? api.listAlerts({ status: 'open' }) : Promise.resolve([]),
      can('clusters:read') ? api.listClusters({ onlyGaps: true, light: true }) : Promise.resolve([]),
      can('cases:read') && supports('cases') ? api.listCases({ status: 'open' }) : Promise.resolve([]),
      can('endusers:read') && supports('endUsers') ? api.listEndUsers('blocked') : Promise.resolve([]),
    ])
      .then(([alerts, gaps, cases, blocked]) =>
        setCounts({
          alerts: alerts.filter((a) => a.status === 'new').length,
          critical: alerts.filter((a) => a.severity === 'critical' && a.status === 'new').length,
          gaps: gaps.filter((g) => (g.gapStatus ? g.gapStatus === 'active' : g.isInformationGap)).length,
          cases: cases.length,
          blocked: blocked.length,
        }),
      )
      .catch(() => {
        // Counters are optional; the pages report their own errors.
      });
  }, [api, can]);

  useEffect(() => {
    refreshCounts();
    const timer = window.setInterval(refreshCounts, 60_000);
    return () => window.clearInterval(timer);
  }, [refreshCounts]);

  if (!user) return null;

  return (
    <CountsContext.Provider value={refreshCounts}>
      <a className="skip-link" href="#content">
        Przejdź do treści
      </a>
      <div className={`shell ${menuOpen ? 'menu-open' : ''}`}>
        <aside className="sidebar" aria-label="Nawigacja główna">
          <div className="brand">
            <Logo size={34} />
            <div>
              <div className="brand-name">Prawdowid</div>
              <div className="brand-sub">Panel administracyjny</div>
            </div>
          </div>
          <nav>
            {NAV.map((group) => {
              const items = group.items.filter((i) => can(i.permission) && (!i.feature || supports(i.feature)));
              if (!items.length) return null;
              return (
                <div key={group.section} className="nav-group">
                  <div className="nav-section">{group.section}</div>
                  {items.map((item) => {
                    const count = item.counter && counts ? counts[item.counter] : 0;
                    const urgent = item.counter === 'alerts' && (counts?.critical ?? 0) > 0;
                    return (
                      <NavLink key={item.to} to={item.to} end={item.to === '/'} className="nav-link" onClick={() => setMenuOpen(false)}>
                        <Icon name={item.icon} size={18} />
                        <span>{item.label}</span>
                        {count > 0 && (
                          <span
                            className={`nav-count ${urgent ? 'is-urgent' : ''}`}
                            aria-label={item.counter === 'blocked' ? `${count} zablokowanych` : `${count} nowych`}
                          >
                            {count}
                          </span>
                        )}
                      </NavLink>
                    );
                  })}
                </div>
              );
            })}
          </nav>
          <div className="sidebar-foot">
            <span className="muted">Źródło danych:</span>{' '}
            {api.mode === 'mock' ? 'przykładowe (mock)' : <code title={api.target}>{api.target}</code>}
          </div>
        </aside>
        <div className="scrim" onClick={() => setMenuOpen(false)} aria-hidden="true" />

        <div className="main-col">
          <header className="topbar">
            <button type="button" className="icon-btn menu-btn" onClick={() => setMenuOpen((o) => !o)} aria-label="Menu">
              <Icon name="menu" />
            </button>
            <div className="topbar-env">
              {api.mode === 'mock' ? (
                <span className="env env-demo" title="Dane generowane w przeglądarce">
                  DEMO · dane przykładowe
                </span>
              ) : (
                <span className="env env-live" title={api.target}>
                  {config.environmentLabel || 'API'} · {api.target}
                </span>
              )}
            </div>
            <div className="topbar-right">
              <button type="button" className="icon-btn" onClick={toggleTheme} aria-label="Przełącz motyw jasny/ciemny">
                <Icon name="moon" className="theme-dark-hide" />
                <Icon name="sun" className="theme-light-hide" />
              </button>
              <div className="user-chip">
                <span className="avatar" aria-hidden="true">
                  {user.name
                    .split(' ')
                    .map((p) => p[0])
                    .slice(0, 2)
                    .join('')}
                </span>
                <span className="user-meta">
                  <span className="user-name">{user.name}</span>
                  <span className="user-role">{ROLE_LABEL[user.role]}</span>
                </span>
              </div>
              {supports('passwords') && (
                <button type="button" className="icon-btn" onClick={() => setChangingPassword(true)} aria-label="Zmień hasło" title="Zmień hasło">
                  <Icon name="lock" />
                </button>
              )}
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => logout()}>
                <Icon name="logout" size={16} />
                <span className="hide-sm">Wyloguj</span>
              </button>
            </div>
          </header>
          {changingPassword && (
            <ChangePasswordModal
              onClose={() => setChangingPassword(false)}
              onChanged={() => logout('Hasło zmienione. Zaloguj się nowym hasłem.')}
            />
          )}
          {api.mode === 'mock' && (
            <div className="demo-banner" role="note">
              <Icon name="info" size={16} />
              <span>
                Tryb demonstracyjny: wszystkie liczby, zapytania i wyniki są przykładowe. Prawdziwe dane z backendu admina:{' '}
                <code>npm run dev</code> (bez <code>--mode demo</code>) albo <code>"dataSource": "http"</code> w{' '}
                <code>config.json</code>.
              </span>
            </div>
          )}
          <main id="content" className="content" tabIndex={-1}>
            <Outlet />
          </main>
        </div>
      </div>
    </CountsContext.Provider>
  );
}

/** Own password change; the backend ends every session of the account, so the panel signs out. */
function ChangePasswordModal({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const api = getApi();
  const { run, busy } = useAction();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [repeat, setRepeat] = useState('');
  const mismatch = repeat.length > 0 && next !== repeat;
  const valid = current.length > 0 && next.length >= 10 && next === repeat;

  const submit = async () => {
    if (await run(() => api.changeOwnPassword(current, next), 'Hasło zmienione.')) onChanged();
  };

  return (
    <Modal
      open
      onClose={onClose}
      title="Zmień hasło"
      footer={
        <>
          <button type="button" className="btn" onClick={onClose}>
            Anuluj
          </button>
          <button type="button" className="btn btn-primary" disabled={busy || !valid} onClick={submit}>
            Zmień hasło
          </button>
        </>
      }
    >
      <div className="stack">
      <Field label="Obecne hasło">
        <input type="password" autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
      </Field>
      <Field label="Nowe hasło" hint="Co najmniej 10 znaków.">
        <input type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
      </Field>
      <Field label="Powtórz nowe hasło" error={mismatch ? 'Hasła nie są takie same.' : null}>
        <input type="password" autoComplete="new-password" value={repeat} onChange={(e) => setRepeat(e.target.value)} />
      </Field>
      <p className="muted small">Po zmianie wszystkie Twoje sesje zostaną zakończone — zalogujesz się ponownie.</p>
      </div>
    </Modal>
  );
}
