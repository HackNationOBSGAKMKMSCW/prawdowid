import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import { useAuth } from '../auth/AuthContext.tsx';
import type { Permission } from '../auth/permissions.ts';
import { getConfig } from '../config.ts';
import { Icon, type IconName, Logo } from './icons.tsx';
import { ROLE_LABEL } from './labels.ts';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  permission: Permission;
  counter?: keyof Counts;
}

export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: 'Przegląd',
    items: [{ to: '/', label: 'Pulpit', icon: 'dashboard', permission: 'dashboard:read' }],
  },
  {
    section: 'Monitoring',
    items: [
      { to: '/alerts', label: 'Alerty i ostrzeżenia', icon: 'bell', permission: 'alerts:read', counter: 'alerts' },
      { to: '/gaps', label: 'Luki informacyjne', icon: 'gap', permission: 'clusters:read', counter: 'gaps' },
      { to: '/repeated', label: 'Powtarzające się zapytania', icon: 'repeat', permission: 'clusters:read' },
      { to: '/security', label: 'Bezpieczeństwo', icon: 'shield', permission: 'security:read' },
    ],
  },
  {
    section: 'Obsługa',
    items: [
      { to: '/cases', label: 'Sprawy moderatora', icon: 'folder', permission: 'cases:read', counter: 'cases' },
      { to: '/checks', label: 'Historia weryfikacji', icon: 'history', permission: 'checks:read' },
    ],
  },
  {
    section: 'Konfiguracja',
    items: [
      { to: '/sources', label: 'Katalog źródeł', icon: 'database', permission: 'sources:read' },
      { to: '/models', label: 'Modele i dostawcy', icon: 'cpu', permission: 'models:read' },
      { to: '/rules', label: 'Reguły alertów', icon: 'sliders', permission: 'rules:read' },
      { to: '/settings', label: 'Kanały i prywatność', icon: 'settings', permission: 'settings:read' },
      { to: '/users', label: 'Użytkownicy', icon: 'users', permission: 'users:read' },
      { to: '/audit', label: 'Dziennik audytu', icon: 'audit', permission: 'audit:read' },
    ],
  },
];

interface Counts {
  alerts: number;
  critical: number;
  gaps: number;
  cases: number;
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
  const [counts, setCounts] = useState<Counts | null>(null);
  const [, toggleTheme] = useTheme();

  const refreshCounts = useCallback(() => {
    Promise.all([
      can('alerts:read') ? api.listAlerts({ status: 'open' }) : Promise.resolve([]),
      can('clusters:read') ? api.listClusters({ onlyGaps: true }) : Promise.resolve([]),
      can('cases:read') ? api.listCases({ status: 'open' }) : Promise.resolve([]),
    ])
      .then(([alerts, gaps, cases]) =>
        setCounts({
          alerts: alerts.filter((a) => a.status === 'new').length,
          critical: alerts.filter((a) => a.severity === 'critical' && a.status === 'new').length,
          gaps: gaps.filter((g) => g.isInformationGap).length,
          cases: cases.length,
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
              const items = group.items.filter((i) => can(i.permission));
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
                          <span className={`nav-count ${urgent ? 'is-urgent' : ''}`} aria-label={`${count} nowych`}>
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
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => logout()}>
                <Icon name="logout" size={16} />
                <span className="hide-sm">Wyloguj</span>
              </button>
            </div>
          </header>
          {api.mode === 'mock' && (
            <div className="demo-banner" role="note">
              <Icon name="info" size={16} />
              <span>
                Tryb demonstracyjny: wszystkie liczby, zapytania i wyniki są przykładowe. Aby podłączyć prawdziwe API,
                ustaw <code>"dataSource": "http"</code> w <code>config.json</code>.
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
