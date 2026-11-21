import { useEffect } from 'react';

/** Ustawia tytuł karty przeglądarki: „<tytuł> – Prawdowid”. */
export function usePageTitle(title: string) {
  useEffect(() => {
    document.title = `${title} – Prawdowid`;
  }, [title]);
}
