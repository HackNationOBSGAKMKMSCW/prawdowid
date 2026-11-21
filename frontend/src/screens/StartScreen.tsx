import type { FormEvent, KeyboardEvent } from 'react';
import { Link } from 'react-router-dom';
import { SOURCE_GROUPS, WHATSAPP_NUMBER } from '../content/sources.ts';
import { VERDICT_ORDER, VERDICTS } from '../content/verdicts.ts';
import { useChecker } from '../lib/checker.ts';

const STEPS = [
  { lead: 'Wklejasz wiadomość', rest: ' albo link do artykułu.' },
  { lead: 'Porównujemy ją', rest: ' z wiarygodnymi źródłami z naszej listy.' },
  { lead: 'Dostajesz wynik', rest: ' i źródła, które możesz sam przeczytać.' },
];

export default function StartScreen() {
  const { input, setInput, error, run } = useChecker();

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    run();
  };

  // Ctrl/Cmd + Enter wysyła formularz, sam Enter dodaje nową linię.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      run();
    }
  };

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="title-xl" tabIndex={-1}>
          Sprawdź wiadomość
        </h1>
        <p className="lead">Wklej to, co dostałeś. Powiemy Ci, co mówią o tym wiarygodne źródła.</p>
      </div>

      <form className="check-form" onSubmit={onSubmit} noValidate>
        <label htmlFor="pw-input" className="field-label">
          Wiadomość lub link
        </label>
        <textarea
          id="pw-input"
          className="textarea"
          rows={5}
          placeholder="Wklej tutaj wiadomość albo link"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          aria-required="true"
          aria-invalid={error}
          aria-describedby={error ? 'pw-err' : undefined}
        />
        {error && (
          <p id="pw-err" className="field-error" role="alert">
            Najpierw wklej wiadomość.
          </p>
        )}
        <button type="submit" className="btn-primary">
          Sprawdź
        </button>
      </form>

      <p className="note note--center">Za darmo, bez logowania.</p>

      <div className="whatsapp">
        <span className="whatsapp__label">Możesz też napisać na WhatsApp:</span>
        <strong className="whatsapp__number">{WHATSAPP_NUMBER}</strong>
      </div>

      <section id="jak" className="panel" aria-labelledby="jak-h">
        <h2 id="jak-h" className="panel__title">
          Jak to działa
        </h2>
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
      </section>

      <section className="panel" aria-labelledby="wyniki-h">
        <h2 id="wyniki-h" className="panel__title">
          Jaki wynik możesz dostać
        </h2>
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
      </section>

      <section id="zrodla" className="panel" aria-labelledby="zrodla-h">
        <h2 id="zrodla-h" className="panel__title">
          Z jakich źródeł korzystamy
        </h2>
        <p className="panel__text">Lista źródeł jest jawna. Każdy może ją sprawdzić.</p>
        <ul className="plain-list">
          {SOURCE_GROUPS.map((group) => (
            <li key={group.name} className="source-groups__item">
              <strong className="source-groups__name">{group.name}</strong>
              <span className="source-groups__examples">{group.examples}</span>
            </li>
          ))}
        </ul>
        <Link to="/zrodla" className="panel__link">
          Zobacz pełną listę źródeł
        </Link>
      </section>
    </div>
  );
}
