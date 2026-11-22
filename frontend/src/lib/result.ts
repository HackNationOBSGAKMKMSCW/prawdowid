import type { CheckResult, Claim, TextAnalysis } from '../api/types.ts';
import { MANIPULATION_FALLBACK_TITLE, MANIPULATION_TITLES, VERDICTS } from '../content/verdicts.ts';
import { SOURCE_NAMES } from '../content/sources.ts';
import { formatDate, plural } from './format.ts';

export type CardTone = 'danger' | 'warning' | 'manipulation';

/** Karta z analizy tekstu: przestarzała data, niespójność, technika manipulacji. */
export interface AnalysisCardView {
  key: string;
  tone: CardTone;
  icon: string;
  title: string;
  quote?: string;
  body: string;
  source?: string;
}

export interface ResultView {
  summary: string;
  claims: Claim[];
  cards: AnalysisCardView[];
  /** Cały wynik jako tekst do czytania na głos. */
  readAloud: string;
}

function analysisCards(
  analysis: TextAnalysis | undefined,
  sourceNames: Record<string, string>,
): AnalysisCardView[] {
  const cards: AnalysisCardView[] = [];
  const dates = analysis?.dates;
  const extracted = dates?.extracted ?? [];

  dates?.issues.forEach((issue, i) => {
    const event = extracted.find((e) => e.start === issue.start);
    if (issue.code === 'OUTDATED_AS_CURRENT') {
      const years = Math.round((issue.delta_days ?? 0) / 365.25);
      const when = years
        ? `około ${years} ${plural(years, 'rok', 'lata', 'lat')} wcześniej`
        : 'dużo wcześniej';
      const date = formatDate(event?.source_date_from);
      cards.push({
        key: `date-${i}`,
        tone: 'danger',
        icon: '!',
        title: 'To stara wiadomość',
        body:
          `Wiadomość mówi, że to dzieje się teraz. Według źródła ${event?.what ?? 'to wydarzenie'} było` +
          (date ? ` ${date}` : '') +
          ` – ${when}.`,
        source: issue.source_id
          ? (sourceNames[issue.source_id] ?? SOURCE_NAMES[issue.source_id] ?? issue.source_id)
          : undefined,
      });
    } else {
      cards.push({
        key: `date-${i}`,
        tone: 'warning',
        icon: '!',
        title: 'Data się nie zgadza',
        body: issue.description ?? 'Daty w tekście nie pasują do siebie.',
      });
    }
  });

  analysis?.manipulation?.fragments.forEach((fragment, i) => {
    cards.push({
      key: `manipulation-${i}`,
      tone: 'manipulation',
      icon: 'Aa',
      title:
        MANIPULATION_TITLES[fragment.category as keyof typeof MANIPULATION_TITLES] ??
        MANIPULATION_FALLBACK_TITLE,
      quote: fragment.quote,
      body: fragment.explanation,
    });
  });

  return cards;
}

function summaryFor(result: CheckResult, cards: AnalysisCardView[]): string {
  const n = result.claims.length;
  if (n === 0 && cards.length > 0) {
    return `Znaleźliśmy ${cards.length} ${plural(cards.length, 'rzecz', 'rzeczy', 'rzeczy')}, na które warto zwrócić uwagę.`;
  }
  if (result.input_type === 'url') return 'Sprawdziliśmy artykuł z linku.';
  if (n > 1)
    return `Sprawdziliśmy ${n} ${plural(n, 'zdanie', 'zdania', 'zdań')} z Twojej wiadomości.`;
  return 'Sprawdziliśmy Twoją wiadomość.';
}

export function buildResultView(result: CheckResult): ResultView {
  const cards = analysisCards(result.analysis, result.source_names ?? {});
  const summary = summaryFor(result, cards);
  const readAloud = [
    'Wynik.',
    summary,
    ...result.claims.map((c) => `${VERDICTS[c.verdict].label}. ${c.text} ${c.explanation}`),
    ...cards.map((k) => `${k.title}. ${k.quote ? `„${k.quote}”. ` : ''}${k.body}`),
  ].join(' ');
  return { summary, claims: result.claims, cards, readAloud };
}
