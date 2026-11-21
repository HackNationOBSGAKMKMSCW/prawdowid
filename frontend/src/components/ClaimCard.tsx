import { useId, useState, type CSSProperties } from 'react';
import type { Claim } from '../api/types.ts';
import { VERDICTS } from '../content/verdicts.ts';

export default function ClaimCard({ claim, index = 0 }: { claim: Claim; index?: number }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const verdict = VERDICTS[claim.verdict];
  const sources = claim.sources ?? [];

  return (
    <article
      className="claim"
      data-verdict={claim.verdict}
      style={{ '--i': index } as CSSProperties}
    >
      <div className="claim__head">
        <span className="dot dot--lg" aria-hidden="true">
          {verdict.icon}
        </span>
        <h2 className="claim__verdict">{verdict.label}</h2>
      </div>
      <div className="claim__body">
        <p className="claim__text">„{claim.text}”</p>
        <p className="claim__explanation">{claim.explanation}</p>
        {sources.length > 0 && (
          <>
            <button
              type="button"
              className="btn-link btn-link--strong"
              aria-expanded={open}
              aria-controls={listId}
              onClick={() => setOpen((o) => !o)}
            >
              {open ? 'Ukryj źródła' : `Pokaż źródła (${sources.length})`}
            </button>
            {open && (
              <ul id={listId} className="plain-list claim-sources">
                {sources.map((source, i) => (
                  <li key={`${source.publisher}-${i}`} className="claim-sources__item">
                    <p className="claim-sources__quote" lang={source.lang ?? 'pl'}>
                      „{source.quote}”
                    </p>
                    <span className="claim-sources__meta">
                      {source.url ? (
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          lang={source.lang ?? 'pl'}
                        >
                          {source.publisher}
                          <span className="sr-only"> (otwiera się w nowej karcie)</span>
                        </a>
                      ) : (
                        <span lang={source.lang ?? 'pl'}>{source.publisher}</span>
                      )}
                      {source.year && `, ${source.year}`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </article>
  );
}
