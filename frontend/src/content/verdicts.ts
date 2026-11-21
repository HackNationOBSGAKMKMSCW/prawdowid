import type { ManipulationCategory, Verdict } from '../api/types.ts';

export interface VerdictInfo {
  /** Nazwa werdyktu pokazywana użytkownikowi. */
  label: string;
  /** Znak w kółku obok werdyktu (dekoracyjny, ukryty dla czytników ekranu). */
  icon: string;
  /** Krótki opis do legendy na stronie startowej. */
  desc: string;
}

/** Kolory werdyktów są zdefiniowane w CSS (`[data-verdict]`), tutaj tylko treści. */
export const VERDICTS: Record<Verdict, VerdictInfo> = {
  confirmed: { label: 'Potwierdzone', icon: '✓', desc: 'wiarygodne źródła mówią to samo.' },
  false: { label: 'Fałszywe', icon: '✕', desc: 'wiarygodne źródła mówią coś innego.' },
  misleading: {
    label: 'Wprowadzające w błąd',
    icon: '!',
    desc: 'część się zgadza, ale brakuje ważnych informacji.',
  },
  insufficient: {
    label: 'Brak wystarczających dowodów',
    icon: '?',
    desc: 'nie znaleźliśmy dość informacji. Nie zgadujemy.',
  },
  unverifiable: {
    label: 'Nie podlega weryfikacji',
    icon: '–',
    desc: 'to czyjaś opinia, a nie fakt.',
  },
};

export const VERDICT_ORDER: Verdict[] = [
  'confirmed',
  'false',
  'misleading',
  'insufficient',
  'unverifiable',
];

/** Nagłówki kart z analizy technik manipulacji. */
export const MANIPULATION_TITLES: Record<ManipulationCategory, string> = {
  EMOTIONAL_LANGUAGE: 'Te słowa mogą grać na emocjach',
  FEAR_APPEAL: 'Te słowa mogą straszyć',
  CONSPIRACY_FRAMING: 'Ten fragment sugeruje spisek',
  FALSE_URGENCY: 'To słowo ma Cię pośpieszyć',
  LACK_OF_SOURCE: 'Tu brakuje źródła',
  EXAGGERATION: 'Ten fragment przesadza',
  CHERRY_PICKING: 'Tu pokazano tylko część faktów',
};

export const MANIPULATION_FALLBACK_TITLE = 'Ten fragment może wpływać na Ciebie';
