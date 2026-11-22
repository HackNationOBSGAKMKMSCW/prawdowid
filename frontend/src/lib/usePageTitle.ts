import { useEffect } from 'react';

/** Ustawia tytuł karty przeglądarki: „<tytuł> – Sprawdź.To”. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} – Sprawdź.To`;
  }, [title]);
}
