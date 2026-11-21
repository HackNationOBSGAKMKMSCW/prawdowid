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
        <Link
          className="whatsapp-link"
          to={input.trim() ? `/whatsapp?text=${encodeURIComponent(input.trim())}` : '/whatsapp'}
        >
          <svg
            className="whatsapp-link__icon"
            viewBox="0 0 24 24"
            width="26"
            height="26"
            aria-hidden="true"
            focusable="false"
          >
            <path
              fill="currentColor"
              d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6.5-.1 1.5-.6 1.7-1.2.2-.6.2-1.1.2-1.2-.1-.1-.2-.2-.5-.3Z"
            />
          </svg>
          <span>
            <span className="whatsapp-link__number">{WHATSAPP_NUMBER}</span>
            <span className="whatsapp-link__hint">
              {input.trim() ? 'Wyślij tę wiadomość na czacie' : 'Otwórz czat'}
            </span>
          </span>
        </Link>
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
