export interface SourceGroup {
  name: string;
  examples: string;
}

/** Skrócona lista grup źródeł pokazywana na stronie startowej. */
export const SOURCE_GROUPS: SourceGroup[] = [
  {
    name: 'Strony rządowe i urzędowe',
    examples: 'gov.pl, Biuletyn Informacji Publicznej, Dziennik Ustaw',
  },
  { name: 'Instytucje naukowe i zdrowotne', examples: 'np. Narodowy Instytut Zdrowia Publicznego' },
  { name: 'Agencje prasowe', examples: 'np. Polska Agencja Prasowa' },
  { name: 'Serwisy sprawdzające fakty', examples: 'np. Demagog, Konkret24' },
  { name: 'Bazy znanych fałszywych wiadomości', examples: 'np. EUvsDisinfo' },
];

export interface ListedSource {
  name: string;
  url?: string;
  note?: string;
}

export interface FullSourceGroup {
  id: string;
  name: string;
  why: string;
  sources: ListedSource[];
}

/** Pełna lista źródeł na stronie „Lista źródeł”. */
export const FULL_SOURCE_LIST: FullSourceGroup[] = [
  {
    id: 'urzedowe',
    name: 'Strony rządowe i urzędowe',
    why: 'Oficjalne informacje państwa: przepisy, komunikaty, decyzje.',
    sources: [
      { name: 'gov.pl', url: 'https://www.gov.pl/', note: 'Serwis Rzeczypospolitej Polskiej' },
      { name: 'Biuletyn Informacji Publicznej', url: 'https://www.gov.pl/web/bip' },
      { name: 'Dziennik Ustaw', url: 'https://dziennikustaw.gov.pl/', note: 'Teksty przepisów' },
    ],
  },
  {
    id: 'nauka',
    name: 'Instytucje naukowe i zdrowotne',
    why: 'Wyniki badań i zalecenia zdrowotne.',
    sources: [
      {
        name: 'Narodowy Instytut Zdrowia Publicznego',
        url: 'https://www.pzh.gov.pl/',
        note: 'Państwowy Zakład Higieny – Państwowy Instytut Badawczy',
      },
      { name: 'Światowa Organizacja Zdrowia (WHO)', url: 'https://www.who.int/' },
    ],
  },
  {
    id: 'agencje',
    name: 'Agencje prasowe',
    why: 'Potwierdzone informacje o bieżących wydarzeniach.',
    sources: [{ name: 'Polska Agencja Prasowa', url: 'https://www.pap.pl/' }],
  },
  {
    id: 'fact-check',
    name: 'Serwisy sprawdzające fakty',
    why: 'Organizacje, które sprawdzają popularne twierdzenia i publikują swoje ustalenia.',
    sources: [
      { name: 'Demagog', url: 'https://demagog.org.pl/' },
      { name: 'Konkret24', url: 'https://konkret24.tvn24.pl/' },
      {
        name: 'Google Fact Check Tools',
        url: 'https://toolbox.google.com/factcheck/explorer',
        note: 'Wyszukiwarka ustaleń serwisów sprawdzających fakty z całego świata',
      },
    ],
  },
  {
    id: 'dezinformacja',
    name: 'Bazy znanych fałszywych wiadomości',
    why: 'Zbiory wiadomości, które już wcześniej okazały się nieprawdziwe.',
    sources: [
      {
        name: 'EUvsDisinfo',
        url: 'https://euvsdisinfo.eu/',
        note: 'Baza Europejskiej Służby Działań Zewnętrznych',
      },
    ],
  },
];

/** Czytelne nazwy identyfikatorów źródeł, które może zwrócić backend. */
export const SOURCE_NAMES: Record<string, string> = {
  pap: 'Polska Agencja Prasowa',
  gov: 'gov.pl',
  nizp: 'Narodowy Instytut Zdrowia Publicznego',
  demagog: 'Demagog',
  konkret24: 'Konkret24',
  euvsdisinfo: 'EUvsDisinfo',
  google_fact_check: 'Google Fact Check Tools',
};

export const WHATSAPP_NUMBER = import.meta.env.VITE_WHATSAPP_NUMBER || '+48 22 000 00 00';

/**
 * Link otwierający czat WhatsApp. Domyślnie `https://wa.me/<numer>`; w dev można
 * ustawić `VITE_WHATSAPP_URL=http://localhost:5174`, żeby otwierać symulator z whatsapp_sim.
 * Wpisana wiadomość trafia do parametru `text` i pojawia się gotowa do wysłania.
 */
export function whatsappUrl(text?: string): string {
  const base =
    import.meta.env.VITE_WHATSAPP_URL || `https://wa.me/${WHATSAPP_NUMBER.replace(/\D/g, '')}`;
  const url = new URL(base, window.location.origin);
  const message = text?.trim();
  if (message) url.searchParams.set('text', message);
  return url.toString();
}
