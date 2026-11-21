/**
 * Przykładowe odpowiedzi do pokazu i pracy bez backendu (VITE_API_MODE=mock).
 * Wszystkie dane są ilustracyjne.
 */
import { truncate } from '../lib/format.ts';
import type { CheckResponse } from './types.ts';

export type Scenario =
  | 'vaccines'
  | 'analysis'
  | 'url'
  | 'opinion'
  | 'clarify'
  | 'scope'
  | 'failure'
  | 'generic';

/** Przykładowe wiadomości, które wkleja pasek demo. */
export const EXAMPLES: Record<Exclude<Scenario, 'generic'>, string> = {
  vaccines: 'Przekaż dalej!!! Szczepionki powodują autyzm. Udowodnił to dr Wakefield w 1998 roku.',
  analysis:
    'PILNE! Właśnie zawalił się most na Wiśle w Toruniu. Dziś w środę 12 marca 2024 policja zamknęła cały rejon.',
  url: 'https://pilne-wiadomosci24.info/niemcy-tajny-plan-granica',
  opinion: 'Polska powinna wydawać więcej na obronność.',
  clarify: 'czy to prawda?',
  scope: 'Jaka będzie jutro pogoda w Krakowie?',
  failure: 'Od poniedziałku zamknięte zostaną przejścia graniczne z Litwą.',
};

/** Prosta klasyfikacja tekstu, żeby tryb demo reagował na dowolną wiadomość. */
export function classify(text: string): Scenario {
  const l = text.toLowerCase();
  if (/^(https?:\/\/|www\.)/.test(l)) return 'url';
  if (/most|toruń|toruniu/.test(l)) return 'analysis';
  if (/szczep|autyzm|wakefield/.test(l)) return 'vaccines';
  if (/pogod|przepis|kredyt|horoskop|lekarz/.test(l)) return 'scope';
  if (/powinn|uważam|myślę|najlepsz|najgorsz/.test(l)) return 'opinion';
  if (l.replace(/[^a-ząćęłńóśźż]/g, '').length < 15) return 'clarify';
  return 'generic';
}

function respond(scenario: Scenario, text: string): CheckResponse {
  const id = `demo-${scenario}`;
  switch (scenario) {
    case 'clarify':
      return { status: 'clarify' };
    case 'scope':
      return { status: 'out_of_scope' };
    case 'failure':
      throw new Error('Symulowana awaria (tryb demo).');
    case 'analysis':
      return {
        status: 'result',
        id,
        input_type: 'text',
        claims: [],
        source_names: { pap: 'Polska Agencja Prasowa' },
        analysis: {
          manipulation: {
            manipulation_detected: true,
            score: 26,
            fragments: [
              {
                quote: 'PILNE!',
                start: 0,
                end: 6,
                category: 'FALSE_URGENCY',
                explanation: 'Nagłówek wywołuje presję czasu bez podania powodu.',
                confidence: 0.9,
              },
            ],
          },
          dates: {
            dates_consistent: false,
            article_date: '2024-03-12',
            issues: [
              {
                code: 'OUTDATED_AS_CURRENT',
                severity: 'high',
                start: 7,
                source_id: 'pap',
                delta_days: 1744,
              },
              {
                code: 'INTERNAL_INCONSISTENCY',
                severity: 'medium',
                start: 52,
                description: 'Tekst podaje, że 12 marca 2024 to środa, ale ten dzień to wtorek.',
              },
            ],
            extracted: [
              { start: 7, what: 'zawalenie mostu w Toruniu', source_date_from: '2019-06-03' },
            ],
          },
        },
      };
    case 'vaccines':
      return {
        status: 'result',
        id,
        input_type: 'text',
        claims: [
          {
            verdict: 'false',
            text: 'Szczepionki powodują autyzm.',
            explanation:
              'Duże badania setek tysięcy dzieci nie wykazały, że szczepionki powodują autyzm.',
            sources: [
              {
                quote: 'Szczepienie MMR nie zwiększa ryzyka autyzmu.',
                publisher: 'Annals of Internal Medicine',
                lang: 'en',
                year: '2019',
                url: 'https://www.acpjournals.org/doi/10.7326/M18-2101',
              },
              {
                quote:
                  'Wyniki badań naukowych nie potwierdzają związku między szczepieniami a występowaniem autyzmu.',
                publisher: 'Narodowy Instytut Zdrowia Publicznego',
                year: '2024',
                url: 'https://szczepienia.pzh.gov.pl/',
              },
              {
                quote:
                  'Twierdzenie o związku szczepionek z autyzmem opiera się na wycofanej publikacji.',
                publisher: 'Demagog',
                year: '2023',
                url: 'https://demagog.org.pl/',
              },
            ],
          },
          {
            verdict: 'misleading',
            text: 'Udowodnił to dr Wakefield w 1998 roku.',
            explanation:
              'Taki artykuł powstał w 1998 roku, ale czasopismo wycofało go w 2010 roku jako nierzetelny.',
            sources: [
              {
                quote: 'Wycofujemy ten artykuł w całości.',
                publisher: 'The Lancet',
                lang: 'en',
                year: '2010',
                url: 'https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(97)11096-0/fulltext',
              },
              {
                quote: 'Panel postanowił o skreśleniu nazwiska z rejestru lekarzy.',
                publisher: 'General Medical Council',
                lang: 'en',
                year: '2010',
              },
            ],
          },
        ],
      };
    case 'url':
      return {
        status: 'result',
        id,
        input_type: 'url',
        claims: [
          {
            verdict: 'insufficient',
            text: 'Niemcy mają tajny plan zamknięcia granicy z Polską w 2027 roku.',
            explanation:
              'Artykuł nie podaje, skąd to wie. Nie znaleźliśmy tej informacji w żadnym wiarygodnym źródle. Przekazaliśmy pytanie ekspertom.',
            sources: [
              {
                quote: 'Zasady przekraczania granicy polsko-niemieckiej nie uległy zmianie.',
                publisher: 'gov.pl',
                year: '2026',
                url: 'https://www.gov.pl/',
              },
            ],
          },
        ],
      };
    case 'opinion':
      return {
        status: 'result',
        id,
        input_type: 'text',
        claims: [
          {
            verdict: 'unverifiable',
            text: truncate(text, 160),
            explanation: 'To czyjaś opinia. Opinii nie da się sprawdzić w źródłach.',
          },
        ],
      };
    case 'generic':
      return {
        status: 'result',
        id,
        input_type: 'text',
        claims: [
          {
            verdict: 'insufficient',
            text: truncate(text, 160),
            explanation: 'Nie znaleźliśmy wiarygodnych źródeł na ten temat. Nie zgadujemy.',
          },
        ],
      };
  }
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer);
      reject(signal.reason ?? new DOMException('Aborted', 'AbortError'));
    });
  });
}

export async function mockCheck(
  text: string,
  scenario: Scenario | undefined,
  signal?: AbortSignal,
): Promise<CheckResponse> {
  const key = scenario ?? classify(text);
  const quick = key === 'clarify' || key === 'scope' || key === 'failure';
  await wait(quick ? 1400 : 2100, signal);
  return respond(key, text);
}
