import { useEffect, useState } from 'react';
import { ApiError, previewLlmInput } from '../api/client.ts';
import type { LlmInputResponse, MaskedLabel } from '../api/types.ts';
import { highlightPlaceholders, MASKED_LABELS } from '../lib/masking.tsx';
import Modal from './Modal.tsx';

type State =
  | { step: 'loading' }
  | { step: 'done'; result: LlmInputResponse }
  | { step: 'error'; message: string };

interface LlmInputDialogProps {
  /** Tekst z formularza; `null` zamyka okno. */
  text: string | null;
  onSend: (text: string) => void;
  onClose: () => void;
}

/**
 * Pokazuje, co po kliknięciu „Sprawdź” trafi do LLM: tekst po sanityzacji
 * i maskowaniu danych osobowych (`POST /api/masking/llm-input`).
 */
export default function LlmInputDialog({ text, onSend, onClose }: LlmInputDialogProps) {
  // Odpowiedź pamięta, dla jakiego tekstu przyszła; inna niż bieżący tekst = ładowanie.
  const [answer, setAnswer] = useState<{ text: string; state: State } | null>(null);
  const state: State = answer && answer.text === text ? answer.state : { step: 'loading' };

  useEffect(() => {
    if (text === null) return;
    const controller = new AbortController();
    previewLlmInput(text, controller.signal).then(
      (result) => setAnswer({ text, state: { step: 'done', result } }),
      (err: unknown) => {
        if (controller.signal.aborted) return;
        setAnswer({
          text,
          state: {
            step: 'error',
            message:
              err instanceof ApiError
                ? `Backend odpowiedział błędem ${err.status}.`
                : 'Brak połączenia z backendem. Czy serwer działa na porcie 8000?',
          },
        });
      },
    );
    return () => controller.abort();
  }, [text]);

  const counts = state.step === 'done' ? Object.entries(state.result.counts) : [];

  return (
    <Modal open={text !== null} onClose={onClose} title="Do LLM trafi ten tekst" wide>
      <p className="modal__text">
        Tak wygląda Twoja wiadomość po zamaskowaniu danych osobowych. Imiona i nazwiska zostają.
      </p>

      <div aria-live="polite" aria-busy={state.step === 'loading'}>
        {state.step === 'loading' && <p className="modal__text">Maskujemy…</p>}
        {state.step === 'error' && (
          <p className="field-error field-error--flat" role="alert">
            {state.message}
          </p>
        )}
        {state.step === 'done' && (
          <div className="masking-result masking-result--flat">
            <p className="masking-output">{highlightPlaceholders(state.result.llm_text)}</p>
            <p className="masking-summary">
              {counts.length === 0
                ? 'Nie znaleziono danych osobowych.'
                : 'Zamaskowano: ' +
                  counts
                    .map(([label, n]) => `${MASKED_LABELS[label as MaskedLabel] ?? label} ×${n}`)
                    .join(', ')}
            </p>
            {state.result.warnings.map((w) => (
              <p key={w} className="masking-note">
                ⚠ {w}
              </p>
            ))}
            <p className="masking-note">Wersja reguł: {state.result.rules_version}</p>
          </div>
        )}
      </div>

      <div className="masking-actions">
        <button
          type="button"
          className="btn-primary btn-primary--md"
          onClick={() => text !== null && onSend(text)}
          data-autofocus
        >
          {state.step === 'error' ? 'Sprawdź mimo to' : 'Wyślij do sprawdzenia'}
        </button>
        <button type="button" className="btn-secondary" onClick={onClose}>
          Anuluj
        </button>
      </div>
    </Modal>
  );
}
