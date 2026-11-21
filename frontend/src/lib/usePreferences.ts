import { useCallback, useEffect, useState } from 'react';

export type Theme = 'light' | 'dark';

export interface Preferences {
  bigText: boolean;
  highContrast: boolean;
  /** Wybrany motyw; `null` = jak w systemie. */
  theme: Theme | null;
}

const STORAGE_KEY = 'prawdowid:preferences';
const DEFAULTS: Preferences = { bigText: false, highContrast: false, theme: null };
const DARK_QUERY = '(prefers-color-scheme: dark)';

function load(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Preferences>;
    return {
      bigText: parsed.bigText === true,
      highContrast: parsed.highContrast === true,
      theme: parsed.theme === 'dark' || parsed.theme === 'light' ? parsed.theme : null,
    };
  } catch {
    return DEFAULTS;
  }
}

function systemTheme(): Theme {
  return typeof window !== 'undefined' && window.matchMedia?.(DARK_QUERY).matches
    ? 'dark'
    : 'light';
}

/**
 * Ustawienia wyglądu (większy tekst, wysoki kontrast, motyw) zapamiętane w
 * przeglądarce. Motyw trafia do `<html data-theme>`, więc obejmuje też okna
 * modalne i widok WhatsApp.
 */
export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(load);
  const [system, setSystem] = useState<Theme>(systemTheme);
  const theme: Theme = prefs.theme ?? system;

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Tryb prywatny lub zablokowana pamięć – ustawienia działają do końca wizyty.
    }
  }, [prefs]);

  // Zmiana motywu w systemie działa, dopóki użytkownik sam nie wybierze motywu.
  useEffect(() => {
    const query = window.matchMedia?.(DARK_QUERY);
    if (!query) return;
    const onChange = () => setSystem(query.matches ? 'dark' : 'light');
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', theme === 'dark' ? '#0e131b' : '#0a2f63');
  }, [theme]);

  const toggleBigText = useCallback(() => setPrefs((p) => ({ ...p, bigText: !p.bigText })), []);
  const toggleHighContrast = useCallback(
    () => setPrefs((p) => ({ ...p, highContrast: !p.highContrast })),
    [],
  );
  const toggleTheme = useCallback(
    () =>
      setPrefs((p) => ({ ...p, theme: (p.theme ?? systemTheme()) === 'dark' ? 'light' : 'dark' })),
    [],
  );

  return { ...prefs, theme, toggleBigText, toggleHighContrast, toggleTheme };
}
