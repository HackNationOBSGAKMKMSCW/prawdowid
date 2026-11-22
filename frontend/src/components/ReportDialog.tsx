import { useState, type FormEvent } from 'react';
import { ApiError, reportCheck, type ReportReason } from '../api/client.ts';
import Modal from './Modal.tsx';

const REASONS: { value: ReportReason; label: string }[] = [
  { value: 'wrong_verdict', label: 'Wynik jest błędny' },
  { value: 'bad_source', label: 'Źródło jest złe albo nie działa' },
  { value: 'misunderstood', label: 'Źle zrozumieliście moją wiadomość' },
  { value: 'other', label: 'Coś innego' },
];

const MAX_COMMENT = 1000;

type Step = 'form' | 'sending' | 'sent';

interface ReportDialogProps {
  open: boolean;
  checkId?: string;
  onClose: () => void;
  /** Wywoływane po udanym wysłaniu. */
  onSent: () => void;
}

export default function ReportDialog({ open, checkId, onClose, onSent }: ReportDialogProps) {
  const [step, setStep] = useState<Step>('form');
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [comment, setComment] = useState('');
  const [missingReason, setMissingReason] = useState(false);
  /** Komunikat o nieudanym wysłaniu; `null` = brak błędu. */
  const [failed, setFailed] = useState<string | null>(null);

  const close = () => {
    onClose();
    // Po wysłaniu następne otwarcie zaczyna od czystego formularza.
    if (step === 'sent') {
      setStep('form');
      setReason(null);
      setComment('');
    }
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!reason) {
      setMissingReason(true);
      document.querySelector<HTMLInputElement>('input[name="report-reason"]')?.focus();
      return;
    }
    setFailed(null);
    setStep('sending');
    try {
      await reportCheck(checkId, { reason, comment: comment.trim() || undefined });
      setStep('sent');
      onSent();
    } catch (err) {
      setStep('form');
      setFailed(reportFailure(err));
    }
  };

  if (step === 'sent') {
    return (
      <Modal open={open} onClose={close} title="Dziękujemy za zgłoszenie" icon="✓" tone="success">
        <p className="modal__text">
          Nasz zespół przejrzy ten wynik. Dzięki Tobie Prawdowid będzie działał lepiej.
        </p>
        <div className="modal__actions">
          <button
            type="button"
            className="btn-primary btn-primary--md"
            onClick={close}
            data-autofocus
          >
            Zamknij
          </button>
        </div>
      </Modal>
    );
  }

  const sending = step === 'sending';

  return (
    <Modal open={open} onClose={close} title="Zgłoś błąd" busy={sending}>
      <p className="modal__text">Napisz nam, co jest nie tak z tym wynikiem.</p>
      <form className="modal__form" onSubmit={onSubmit} noValidate>
        <fieldset
          className="choice-group"
          aria-describedby={missingReason ? 'report-reason-err' : undefined}
          aria-invalid={missingReason}
        >
          <legend className="choice-group__legend">Co jest nie tak?</legend>
          {REASONS.map((r) => (
            <label key={r.value} className="choice">
              <input
                type="radio"
                name="report-reason"
                value={r.value}
                checked={reason === r.value}
                onChange={() => {
                  setReason(r.value);
                  setMissingReason(false);
                }}
                disabled={sending}
              />
              <span>{r.label}</span>
            </label>
          ))}
          {missingReason && (
            <p id="report-reason-err" className="field-error field-error--flat" role="alert">
              Wybierz, co jest nie tak.
            </p>
          )}
        </fieldset>

        <div className="modal__field">
          <label htmlFor="report-comment" className="modal__label">
            Opisz krótko <span className="modal__optional">(nieobowiązkowe)</span>
          </label>
          <textarea
            id="report-comment"
            className="textarea textarea--sm"
            rows={3}
            maxLength={MAX_COMMENT}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Np. który fragment jest błędny i dlaczego"
            disabled={sending}
          />
        </div>

        {failed && (
          <p className="field-error field-error--flat" role="alert">
            {failed}
          </p>
        )}

        <div className="modal__actions">
          <button type="submit" className="btn-primary btn-primary--md" disabled={sending}>
            {sending ? 'Wysyłamy…' : 'Wyślij zgłoszenie'}
          </button>
          <button type="button" className="btn-secondary" onClick={close} disabled={sending}>
            Anuluj
          </button>
        </div>
      </form>
    </Modal>
  );
}

function reportFailure(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'result_not_found') {
      return 'Ten wynik już wygasł albo nie został zapisany. Sprawdź wiadomość jeszcze raz i zgłoś nowy wynik.';
    }
    if (err.code === 'network') return 'Brak połączenia z serwerem. Sprawdź internet i spróbuj jeszcze raz.';
    if (err.code === 'storage_unavailable') return 'Nie możemy teraz zapisać zgłoszenia. Spróbuj za chwilę.';
  }
  return 'Nie udało się wysłać zgłoszenia. Spróbuj jeszcze raz.';
}
