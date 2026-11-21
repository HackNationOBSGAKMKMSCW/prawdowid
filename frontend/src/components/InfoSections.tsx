import { useId, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { FULL_SOURCE_LIST, WHATSAPP_NUMBER } from '../content/sources.ts';
import { VERDICT_ORDER, VERDICTS } from '../content/verdicts.ts';

/**
 * Treści informacyjne używane w dwóch miejscach: w oknach otwieranych ze stopki
 * (nagłówki h3) i na podstronach /zrodla, /pomoc, /deklaracja-dostepnosci (h2).
 */
type Level = 2 | 3;

function Section({ level, title, children }: { level: Level; title: string; children: ReactNode }) {
  const id = useId();
  const H = level === 2 ? 'h2' : 'h3';
  return (
    <section className="panel" aria-labelledby={id}>
      <H id={id} className="panel__title">
        {title}
      </H>
      {children}
    </section>
  );
}

const STEPS = [
  { lead: 'Wklejasz wiadomość', rest: ' albo link do artykułu.' },
  { lead: 'Porównujemy ją', rest: ' z wiarygodnymi źródłami z naszej listy.' },
  { lead: 'Dostajesz wynik', rest: ' i źródła, które możesz sam przeczytać.' },
];

export function HowItWorksContent({ level }: { level: Level }) {
  return (
    <>
      <Section level={level} title="Trzy kroki">
        <ol className="plain-list steps">
          {STEPS.map((step, i) => (
            <li key={step.lead} className="steps__item">
              <span className="dot" aria-hidden="true">
                {i + 1}
              </span>
              <span className="steps__text">
                <strong>{step.lead}</strong>
                {step.rest}
              </span>
            </li>
          ))}
        </ol>
      </Section>
      <Section level={level} title="Jaki wynik możesz dostać">
        <ul className="plain-list legend">
          {VERDICT_ORDER.map((key) => (
            <li key={key} className="legend__item" data-verdict={key}>
              <span className="dot dot--sm" aria-hidden="true">
                {VERDICTS[key].icon}
              </span>
              <span className="legend__text">
                <strong className="legend__name">{VERDICTS[key].label}</strong> –{' '}
                {VERDICTS[key].desc}
              </span>
            </li>
          ))}
        </ul>
      </Section>
      <Section level={level} title="Na co jeszcze patrzymy">
        <div className="prose">
          <ul>
            <li>Czy wiadomość nie jest stara, choć udaje nową.</li>
            <li>Czy daty w tekście się zgadzają.</li>
            <li>Czy tekst nie gra na emocjach, nie straszy i nie pogania.</li>
          </ul>
        </div>
      </Section>
    </>
  );
}

export function SourcesContent({ level }: { level: Level }) {
  return (
    <>
      {FULL_SOURCE_LIST.map((group) => (
        <Section key={group.id} level={level} title={group.name}>
          <p className="panel__text">{group.why}</p>
          <ul className="plain-list">
            {group.sources.map((source) => (
              <li key={source.name} className="source-groups__item">
                <strong className="source-groups__name">
                  {source.url ? (
                    <a href={source.url} target="_blank" rel="noopener noreferrer">
                      {source.name}
                      <span className="sr-only"> (otwiera się w nowej karcie)</span>
                    </a>
                  ) : (
                    source.name
                  )}
                </strong>
                {source.note && <span className="source-groups__examples">{source.note}</span>}
              </li>
            ))}
          </ul>
        </Section>
      ))}
      <p className="note note--muted">
        Znasz wiarygodne źródło, którego tu brakuje? Napisz do nas przez Pomoc.
      </p>
    </>
  );
}

export function HelpContent({ onShowSources }: { onShowSources?: () => void }) {
  const sourcesLink = onShowSources ? (
    <button type="button" className="inline-link" onClick={onShowSources}>
      jawnej listy źródeł
    </button>
  ) : (
    <Link to="/zrodla">jawnej listy źródeł</Link>
  );

  const questions: { q: string; a: ReactNode }[] = [
    {
      q: 'Co mogę sprawdzić?',
      a: 'Wiadomości o sprawach publicznych: polityce, zdrowiu publicznym, bezpieczeństwie, wydarzeniach w kraju i na świecie. Możesz wkleić tekst wiadomości, wpis z internetu albo link do artykułu.',
    },
    {
      q: 'Czego nie sprawdzamy?',
      a: 'Nie odpowiadamy na pytania o pogodę, Twoje zdrowie czy pieniądze. Nie oceniamy opinii – opinii nie da się sprawdzić w źródłach.',
    },
    {
      q: 'Skąd wiecie, co jest prawdą?',
      a: (
        <>
          Porównujemy wiadomość z wiarygodnymi źródłami z naszej {sourcesLink}. Przy każdym wyniku
          pokazujemy źródła, żebyś mógł je sam przeczytać.
        </>
      ),
    },
    {
      q: 'Co znaczy „Brak wystarczających dowodów”?',
      a: 'Nie znaleźliśmy dość informacji w wiarygodnych źródłach. Wtedy nie zgadujemy. To nie znaczy, że wiadomość jest fałszywa ani że jest prawdziwa.',
    },
    { q: 'Czy muszę się logować?', a: 'Nie. Prawdowid jest za darmo i bez logowania.' },
    {
      q: 'Co dzieje się z moją wiadomością?',
      a: 'Używamy jej tylko do sprawdzenia wyniku.',
    },
    {
      q: 'Wynik jest błędny. Co zrobić?',
      a: 'Kliknij „Zgłoś błąd” pod wynikiem i napisz, co jest nie tak. Nasz zespół przejrzy zgłoszenie.',
    },
  ];

  return (
    <>
      <div className="faq">
        {questions.map(({ q, a }) => (
          <details key={q} className="faq__item">
            <summary className="faq__question">{q}</summary>
            <p className="faq__answer">{a}</p>
          </details>
        ))}
      </div>
      <div className="whatsapp">
        <span className="whatsapp__label">Wolisz zapytać na WhatsApp? Napisz:</span>
        <strong className="whatsapp__number">{WHATSAPP_NUMBER}</strong>
      </div>
    </>
  );
}

export function AccessibilityContent({ level }: { level: Level }) {
  return (
    <>
      <Section level={level} title="Ułatwienia">
        <div className="prose">
          <ul>
            <li>
              <strong>Większy tekst</strong> – ikona „aA” w nagłówku powiększa całą stronę.
            </li>
            <li>
              <strong>Ciemny motyw</strong> – ikona księżyca w nagłówku. Domyślnie strona dopasowuje
              się do ustawień telefonu lub komputera.
            </li>
            <li>
              <strong>Wysoki kontrast</strong> – ikona półkola w nagłówku: czarny tekst na białym
              tle, podkreślone linki.
            </li>
            <li>
              <strong>Przeczytaj na głos</strong> – wynik może przeczytać syntezator mowy Twojej
              przeglądarki.
            </li>
            <li>
              Całą stronę obsłużysz klawiaturą. Na początku strony jest link „Przejdź do treści”.
            </li>
            <li>Strona działa z czytnikami ekranu i szanuje ustawienie ograniczenia animacji.</li>
            <li>Piszemy prostym językiem, krótkimi zdaniami.</li>
          </ul>
        </div>
      </Section>
      <Section level={level} title="Zgodność">
        <div className="prose">
          <p>
            Strona jest projektowana zgodnie z wytycznymi WCAG 2.1 na poziomie AA. Wersja
            demonstracyjna nie przeszła jeszcze niezależnego audytu dostępności.
          </p>
        </div>
      </Section>
      <Section level={level} title="Coś nie działa?">
        <div className="prose">
          <p>
            Jeśli coś utrudnia Ci korzystanie z serwisu, napisz do nas przez Pomoc. Opisz, co nie
            działa i na jakim urządzeniu.
          </p>
        </div>
      </Section>
    </>
  );
}
