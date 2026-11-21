import InfoPage from './InfoPage.tsx';

export default function AccessibilityPage() {
  return (
    <InfoPage
      title="Deklaracja dostępności"
      lead="Chcemy, żeby z Prawdowida mógł korzystać każdy, także osoby z niepełnosprawnościami i osoby starsze."
    >
      <section className="panel" aria-labelledby="a11y-features">
        <h2 id="a11y-features" className="panel__title">
          Ułatwienia
        </h2>
        <div className="prose">
          <ul>
            <li>
              <strong>Większy tekst</strong> – przycisk w nagłówku powiększa całą stronę.
            </li>
            <li>
              <strong>Wysoki kontrast</strong> – czarny tekst na białym tle, podkreślone linki.
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
      </section>

      <section className="panel" aria-labelledby="a11y-status">
        <h2 id="a11y-status" className="panel__title">
          Zgodność
        </h2>
        <div className="prose">
          <p>
            Strona jest projektowana zgodnie z wytycznymi WCAG 2.1 na poziomie AA. Wersja
            demonstracyjna nie przeszła jeszcze niezależnego audytu dostępności.
          </p>
        </div>
      </section>

      <section className="panel" aria-labelledby="a11y-contact">
        <h2 id="a11y-contact" className="panel__title">
          Coś nie działa?
        </h2>
        <div className="prose">
          <p>
            Jeśli coś utrudnia Ci korzystanie z serwisu, napisz do nas przez stronę Pomoc. Opisz, co
            nie działa i na jakim urządzeniu.
          </p>
        </div>
      </section>
    </InfoPage>
  );
}
