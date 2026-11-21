import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { WHATSAPP_NUMBER } from '../content/sources.ts';
import InfoPage from './InfoPage.tsx';

const QUESTIONS: { q: string; a: ReactNode }[] = [
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
        Porównujemy wiadomość z wiarygodnymi źródłami z naszej{' '}
        <Link to="/zrodla">jawnej listy źródeł</Link>. Przy każdym wyniku pokazujemy źródła, żebyś
        mógł je sam przeczytać.
      </>
    ),
  },
  {
    q: 'Co znaczy „Brak wystarczających dowodów”?',
    a: 'Nie znaleźliśmy dość informacji w wiarygodnych źródłach. Wtedy nie zgadujemy. To nie znaczy, że wiadomość jest fałszywa ani że jest prawdziwa.',
  },
  {
    q: 'Czy muszę się logować?',
    a: 'Nie. Prawdowid jest za darmo i bez logowania.',
  },
  {
    q: 'Co dzieje się z moją wiadomością?',
    a: 'Używamy jej tylko do sprawdzenia. Na stronie wyniku możesz kliknąć „Usuń moje dane”, a usuniemy ją od razu.',
  },
  {
    q: 'Wynik jest błędny. Co zrobić?',
    a: 'Kliknij „Zgłoś błąd” pod wynikiem. Nasz zespół przejrzy zgłoszenie.',
  },
];

export default function HelpPage() {
  return (
    <InfoPage title="Pomoc" lead="Odpowiedzi na najczęstsze pytania.">
      {QUESTIONS.map(({ q, a }, i) => (
        <section key={q} className="panel" aria-labelledby={`faq-${i}`}>
          <h2 id={`faq-${i}`} className="panel__title">
            {q}
          </h2>
          <div className="prose">
            <p>{a}</p>
          </div>
        </section>
      ))}
      <div className="whatsapp">
        <span className="whatsapp__label">Wolisz zapytać na WhatsApp? Napisz:</span>
        <strong className="whatsapp__number">{WHATSAPP_NUMBER}</strong>
      </div>
    </InfoPage>
  );
}
