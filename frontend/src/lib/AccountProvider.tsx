import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  ACCOUNTS_ENABLED,
  ApiError,
  changePassword as apiChangePassword,
  fetchAccount,
  setAuthToken,
  signIn as apiSignIn,
  signOut as apiSignOut,
  signUp as apiSignUp,
  type Account,
  type AccountSession,
} from '../api/client.ts';
import { AccountContext, type AccountState, type AccountStatus } from './account.ts';

const STORAGE_KEY = 'prawdowid:session';

/** Sesja zapisana w przeglądarce; wygasła albo uszkodzona = brak sesji. */
function loadSession(): AccountSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw) as AccountSession;
    if (!session?.token || !session.user) return null;
    if (session.expiresAt && Date.parse(session.expiresAt) <= Date.now()) return null;
    return session;
  } catch {
    return null;
  }
}

function saveSession(session: AccountSession | null): void {
  try {
    if (session) localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Prywatne okno albo zablokowany localStorage: sesja trwa do zamknięcia karty.
  }
}

/**
 * Konto użytkownika strony. Token sesji z `/api/auth` jest w `localStorage`, a klient API
 * dołącza go do każdego zapytania — dzięki temu sprawdzenia trafiają do historii konta.
 */
export function AccountProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<AccountSession | null>(() => {
    const stored = ACCOUNTS_ENABLED ? loadSession() : null;
    setAuthToken(stored?.token ?? null);
    return stored;
  });
  const [status, setStatus] = useState<AccountStatus>(session ? 'loading' : 'signed_out');

  const apply = useCallback((next: AccountSession | null) => {
    setAuthToken(next?.token ?? null);
    saveSession(next);
    setSession(next);
    setStatus(next ? 'signed_in' : 'signed_out');
  }, []);

  // Przy wejściu na stronę: czy zapisana sesja jest nadal ważna (konto aktywne, token nieodwołany).
  useEffect(() => {
    if (!session || status !== 'loading') return;
    const controller = new AbortController();
    fetchAccount(controller.signal)
      .then((user: Account) => apply({ ...session, user }))
      .catch((err: unknown) => {
        if ((err as Error).name === 'AbortError') return;
        // Brak połączenia: zostajemy zalogowani; odrzucony token: wylogowanie.
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) apply(null);
        else setStatus('signed_in');
      });
    return () => controller.abort();
  }, [session, status, apply]);

  const value = useMemo<AccountState>(
    () => ({
      status,
      user: status === 'signed_in' ? (session?.user ?? null) : null,
      signIn: async (email, password) => apply(await apiSignIn(email.trim(), password)),
      signUp: async (name, email, password) =>
        apply(await apiSignUp(name.trim(), email.trim(), password)),
      signOut: async () => {
        await apiSignOut();
        apply(null);
      },
      changePassword: async (current, next) => {
        await apiChangePassword(current, next);
        apply(null);
      },
    }),
    [status, session, apply],
  );

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}
