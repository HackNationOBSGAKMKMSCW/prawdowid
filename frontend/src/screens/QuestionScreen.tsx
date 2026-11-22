import { useState, type FormEvent, type KeyboardEvent } from 'react';
import type { ClarifyStep } from '../api/types.ts';
import { useChecker } from '../lib/checker.ts';

/**
 * Pytania o szczegóły, zanim sprawdzimy wiadomość o konkretnym zdarzeniu
 * (np. „Czy spadł dron w Polsce?” – kiedy i gdzie?).
 */
export default function QuestionScreen({ step, round }: { step: ClarifyStep; round: number }) {
  const { answer, skipQuestions, goStart } = useChecker();
  const [value, setValue] = useState('');
  const [error, setError] = useState(false);

  const submit = () => {
    if (!value.trim()) {
      setError(true);
      return;
    }
    answer(value);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  // Jak w formularzu startowym: Ctrl/Cmd + Enter wysyła, sam Enter dodaje nową linię.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submit();
    }
  };

  const single = step.questions.length === 1;

  return (
    <div className="page page--question">
      <div className="page__head">
        <h1 className="title-l" tabIndex={-1}>
          {round > 1 ? 'Jeszcze jedno pytanie' : 'Doprecyzuj, o co chodzi'}
        </h1>
        <p className="lead">
          Ta wiadomość dotyczy konkretnego zdarzenia. Żeby znaleźć właściwe źródła, potrzebujemy{' '}
          {single ? 'jednego szczegółu' : 'kilku szczegółów'}.
        </p>
      </div>

      {step.understood_claim && (
        <p className="question__understood">
          <span className="question__understood-label">Rozumiemy, że chodzi o:</span>{' '}
          <q>{step.understood_claim}</q>
        </p>
      )}

      <form className="check-form" onSubmit={onSubmit} noValidate>
        <ul id="pw-questions" className="plain-list question__list">
          {step.questions.map((question) => (
            <li key={question} className="question__item">
              <span className="dot dot--sm" aria-hidden="true">
                ?
              </span>
              <span>{question}</span>
            </li>
          ))}
        </ul>
        <label htmlFor="pw-answer" className="field-label">
          Twoja odpowiedź
        </label>
        <textarea
          id="pw-answer"
          className="textarea"
          rows={3}
          placeholder="Np. wczoraj wieczorem, koło Rzeszowa"
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            setError(false);
          }}
          onKeyDown={onKeyDown}
          aria-required="true"
          aria-invalid={error}
          aria-describedby={error ? 'pw-questions pw-answer-err' : 'pw-questions'}
        />
        {error && (
          <p id="pw-answer-err" className="field-error" role="alert">
            Napisz odpowiedź albo wybierz „Sprawdź bez tego”.
          </p>
        )}
        <button type="submit" className="btn-primary">
          Wyślij odpowiedź
        </button>
      </form>

      <div className="actions">
        <button type="button" className="btn-secondary" onClick={skipQuestions}>
          Sprawdź bez tego
        </button>
        <button type="button" className="btn-link" onClick={() => goStart(false)}>
          Anuluj i wróć do wiadomości
        </button>
      </div>

      <p className="note note--muted">
        Wystarczy w przybliżeniu. Nie wiesz? Wybierz „Sprawdź bez tego” – sprawdzimy to, co już
        wiemy.
      </p>
    </div>
  );
}
