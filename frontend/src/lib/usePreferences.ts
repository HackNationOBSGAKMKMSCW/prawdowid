import { useCallback, useEffect, useState } from 'react';

export interface Preferences {
  bigText: boolean;
  highContrast: boolean;
}

const STORAGE_KEY = 'prawdowid:preferences';
const DEFAULTS: Preferences = { bigText: false, highContrast: false };

function load(): Preferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<Preferences>;
    return {
      bigText: parsed.bigText === true,
      highContrast: parsed.highContrast === true,
    };
  } catch {
    return DEFAULTS;
  }
}

/** Ustawienia wyglądu (większy tekst, wysoki kontrast) zapamiętane w przeglądarce. */
export function usePreferences() {
  const [prefs, setPrefs] = useState<Preferences>(load);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
    } catch {
      // Tryb prywatny lub zablokowana pamięć – ustawienia działają do końca wizyty.
    }
  }, [prefs]);

  const toggleBigText = useCallback(() => setPrefs((p) => ({ ...p, bigText: !p.bigText })), []);
  const toggleHighContrast = useCallback(
    () => setPrefs((p) => ({ ...p, highContrast: !p.highContrast })),
    [],
  );

  return { ...prefs, toggleBigText, toggleHighContrast };
}
