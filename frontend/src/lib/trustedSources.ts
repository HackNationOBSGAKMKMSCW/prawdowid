import { useEffect, useState } from 'react';
import { listTrustedSources, type TrustedSource } from '../api/client.ts';
import { FULL_SOURCE_LIST, type FullSourceGroup } from '../content/sources.ts';

/** Grupy dla `trust` z `GET /api/trusted-sources`, w tej kolejności. */
const TRUST_GROUPS: { trust: string; id: string; name: string; why: string }[] = [
  {
    trust: 'official',
    id: 'urzedowe',
    name: 'Strony urzędowe i instytucje publiczne',
    why: 'Oficjalne informacje państwa i instytucji: przepisy, komunikaty, decyzje, ostrzeżenia.',
  },
  {
    trust: 'fact_checker',
    id: 'fact-check',
    name: 'Serwisy sprawdzające fakty',
    why: 'Organizacje, które sprawdzają popularne twierdzenia i publikują swoje ustalenia.',
  },
  {
    trust: 'other',
    id: 'inne',
    name: 'Inne wiarygodne źródła',
    why: 'Pozostałe źródła z naszej listy.',
  },
];

export function groupSources(sources: TrustedSource[]): FullSourceGroup[] {
  const known = new Set(TRUST_GROUPS.map((g) => g.trust));
  return TRUST_GROUPS.map((group) => ({
    id: group.id,
    name: group.name,
    why: group.why,
    sources: sources
      .filter((s) => s.trust === group.trust || (group.trust === 'other' && !known.has(s.trust)))
      .sort((a, b) => a.name.localeCompare(b.name, 'pl'))
      .map((s) => ({
        name: s.name,
        url: s.url,
        note: s.description || s.topics.join(', ') || undefined,
      })),
  })).filter((group) => group.sources.length > 0);
}

export type SourceListState =
  | { status: 'loading' }
  | { status: 'error' }
  /** `demo`: tryb mock bez backendu, lista przykładowa z kodu. */
  | { status: 'ready'; groups: FullSourceGroup[]; demo: boolean };

/**
 * Lista źródeł z bazy (`GET /api/trusted-sources`, tabela edytowana w panelu admina).
 * Nie ma zapasowej listy z kodu: gdy serwer nie odpowiada, strona mówi o tym wprost.
 * Tylko tryb mock (bez backendu) pokazuje przykładową listę.
 */
export function useTrustedSourceGroups(): SourceListState {
  const [state, setState] = useState<SourceListState>({ status: 'loading' });
  useEffect(() => {
    const ctrl = new AbortController();
    listTrustedSources(ctrl.signal).then(
      (sources) => {
        setState(
          sources === null
            ? { status: 'ready', groups: FULL_SOURCE_LIST, demo: true }
            : { status: 'ready', groups: groupSources(sources), demo: false },
        );
      },
      () => {
        if (!ctrl.signal.aborted) setState({ status: 'error' });
      },
    );
    return () => ctrl.abort();
  }, []);
  return state;
}

/** Krótki opis grupy na stronę startową: kilka nazw z listy. */
export function groupExamples(group: FullSourceGroup, limit = 3): string {
  const names = group.sources.slice(0, limit).map((s) => s.name);
  const rest = group.sources.length - names.length;
  return rest > 0 ? `${names.join(', ')} i jeszcze ${rest}` : names.join(', ');
}
