import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { getApi } from '../api/index.ts';
import type { Session, User } from '../api/types.ts';
import { EmptyState } from '../components/ui.tsx';
import { can, type Permission } from './permissions.ts';

// sessionStorage: the session ends with the browser tab, unlike localStorage.
const SESSION_KEY = 'prawdowid-admin-session';

interface AuthValue {
  user: User | null;
  session: Session | null;
  /** Why the user was signed out (shown on the login screen). */
  notice: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: (notice?: string) => void;
  can: (permission: Permission) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

function readStoredSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as Session;
    if (!session?.token || Date.parse(session.expiresAt) <= Date.now()) return null;
    return session;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const api = getApi();
  const [session, setSession] = useState<Session | null>(() => {
    const stored = readStoredSession();
    api.setToken(stored?.token ?? null);
    return stored;
  });
  const [notice, setNotice] = useState<string | null>(null);

  const logout = useCallback(
    (reason?: string) => {
      void api.logout();
      api.setToken(null);
      try {
        sessionStorage.removeItem(SESSION_KEY);
      } catch {
        // ignore
      }
      setSession(null);
      setNotice(reason ?? null);
    },
    [api],
  );

  useEffect(() => {
    api.onUnauthorized(() => logout('Sesja wygasła. Zaloguj się ponownie.'));
  }, [api, logout]);

  // Sign out when the session expires, even if the tab stays open.
  useEffect(() => {
    if (!session) return;
    const ms = Date.parse(session.expiresAt) - Date.now();
    const timer = window.setTimeout(() => logout('Sesja wygasła. Zaloguj się ponownie.'), Math.max(0, ms));
    return () => window.clearTimeout(timer);
  }, [session, logout]);

  const login = useCallback(
    async (email: string, password: string) => {
      const next = await api.login(email, password);
      api.setToken(next.token);
      try {
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(next));
      } catch {
        // Session works until reload.
      }
      setNotice(null);
      setSession(next);
    },
    [api],
  );

  const value = useMemo<AuthValue>(
    () => ({
      user: session?.user ?? null,
      session,
      notice,
      login,
      logout,
      can: (permission) => can(session?.user, permission),
    }),
    [session, notice, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

export function RequirePermission({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { can: allowed } = useAuth();
  if (!allowed(permission)) {
    return (
      <EmptyState title="Brak dostępu" icon="lock">
        Twoja rola nie ma uprawnień do tego widoku. Skontaktuj się z administratorem systemu.
      </EmptyState>
    );
  }
  return <>{children}</>;
}
