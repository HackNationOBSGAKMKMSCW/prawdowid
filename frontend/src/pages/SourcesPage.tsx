import { FULL_SOURCE_LIST } from '../content/sources.ts';
import InfoPage from './InfoPage.tsx';

export default function SourcesPage() {
  return (
    <InfoPage
      title="Lista źródeł"
      lead="Porównujemy wiadomości tylko ze źródłami z tej listy. Lista jest jawna, żeby każdy mógł ją sprawdzić."
    >
      {FULL_SOURCE_LIST.map((group) => (
        <section key={group.name} className="panel" aria-labelledby={`src-${group.id}`}>
          <h2 id={`src-${group.id}`} className="panel__title">
            {group.name}
          </h2>
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
        </section>
      ))}
      <p className="note note--muted">
        Znasz wiarygodne źródło, którego tu brakuje? Napisz do nas przez stronę Pomoc.
      </p>
    </InfoPage>
  );
}
