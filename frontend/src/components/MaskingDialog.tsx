import { useRef, useState, type FormEvent } from 'react';
import { ApiError, maskText } from '../api/client.ts';
import type { MaskingResponse } from '../api/types.ts';
import { highlightPlaceholders, MASKED_LABELS } from '../lib/masking.tsx';
import Modal from './Modal.tsx';

const EXAMPLE =
  'Anna Nowak (PESEL 44051401359, tel. +48 600 100 200, anna.nowak@gmail.com) mieszka przy ' +
  'ul. Polnej 3/14, 61-001 Poznań. Konto: PL61 1090 1014 0000 0712 1981 2874, dowód ABA300000.\n' +
  'Minister Jan Kowalski powiedział, że budżet wyniesie 500 000 000 zł, a inflacja 3,5% ' +
  '(Dz.U. 2024 poz. 1234).';

const MAX_LENGTH = 15_000;

type State =
  | { step: 'idle' }
  | { step: 'sending' }
  | { step: 'done'; input: string; result: MaskingResponse }
  | { step: 'error'; message: string };

interface MaskingDialogProps {
  open: boolean;
  onClose: () => void;
}

/** Okno testowe: wysyła tekst do `POST /api/masking` i pokazuje, co zostało zamaskowane. */
export default function MaskingDialog({ open, onClose }: MaskingDialogProps) {
  const [text, setText] = useState('');
  const [state, setState] = useState<State>({ step: 'idle' });
  const abort = useRef<AbortController | null>(null);

  const close = () => {
    abort.current?.abort();
    onClose();
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const input = text;
    if (!input.trim()) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setState({ step: 'sending' });
    try {
      const result = await maskText(input, controller.signal);
      setState({ step: 'done', input, result });
    } catch (err) {
      if (controller.signal.aborted) return;
      setState({
        step: 'error',
        message:
          err instanceof ApiError
            ? `Backend odpowiedział błędem ${err.status}.`
            : 'Brak połączenia z backendem. Czy serwer działa na porcie 8000?',
      });
    }
  };

  const sending = state.step === 'sending';

  return (
    <Modal open={open} onClose={close} title="Test maskowania danych" wide>
      <p className="modal__text">
        Wpisz tekst z danymi osobowymi. Backend zamaskuje wszystko poza imieniem i nazwiskiem, bez
        użycia LLM.
      </p>
      <form className="modal__form" onSubmit={onSubmit}>
        <div className="modal__field">
          <label htmlFor="masking-input" className="modal__label">
            Tekst do zamaskowania
          </label>
          <textarea
            id="masking-input"
            className="textarea textarea--sm"
            rows={5}
            maxLength={MAX_LENGTH}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Np. Jan Kowalski, tel. 600 100 200, PESEL 44051401359"
            data-autofocus
          />
        </div>
        <div className="masking-actions">
          <button
            type="submit"
            className="btn-primary btn-primary--md"
            disabled={sending || !text.trim()}
          >
            {sending ? 'Maskujemy…' : 'Zamaskuj'}
          </button>
          <button type="button" className="btn-secondary" onClick={() => setText(EXAMPLE)}>
            Wstaw przykład
          </button>
        </div>
      </form>

      <div aria-live="polite">
        {state.step === 'error' && (
          <p className="field-error field-error--flat" role="alert">
            {state.message}
          </p>
        )}
        {state.step === 'done' && <MaskingResult input={state.input} result={state.result} />}
      </div>
    </Modal>
  );
}

function MaskingResult({ input, result }: { input: string; result: MaskingResponse }) {
  // Ta sama wartość w kilku miejscach ma jeden znacznik – w tabeli pokazujemy ją raz.
  const rows = [...new Map(result.entities.map((e) => [e.placeholder, e])).values()];

  return (
    <section className="masking-result" aria-label="Wynik maskowania">
      <h3 className="masking-result__title">Po maskowaniu</h3>
      <p className="masking-output">{highlightPlaceholders(result.masked_text)}</p>

      {rows.length === 0 ? (
        <p className="modal__text">Nie znaleziono danych osobowych.</p>
      ) : (
        <>
          <h3 className="masking-result__title">Zamaskowane dane ({result.entities.length})</h3>
          <div className="masking-table-wrap">
            <table className="masking-table">
              <thead>
                <tr>
                  <th scope="col">Znacznik</th>
                  <th scope="col">Typ</th>
                  <th scope="col">Oryginał</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((e) => (
                  <tr key={e.placeholder}>
                    <td>
                      <mark className="masking-tag">{e.placeholder}</mark>
                    </td>
                    <td>{MASKED_LABELS[e.label] ?? e.label}</td>
                    <td className="masking-table__value">{input.slice(e.start, e.end)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="masking-note">
            Kolumna „Oryginał” powstaje w przeglądarce z wpisanego tekstu – backend nie odsyła
            zamaskowanych wartości.
          </p>
        </>
      )}
      <p className="masking-note">Wersja reguł: {result.rules_version}</p>
    </section>
  );
}
