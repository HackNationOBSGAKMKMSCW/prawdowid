import { useState } from 'react';
import { deleteCheck } from '../api/client.ts';
import Modal from './Modal.tsx';

type Step = 'confirm' | 'deleting' | 'deleted';

interface DeleteDialogProps {
  open: boolean;
  checkId?: string;
  onClose: () => void;
  /** Wywoływane po usunięciu danych. */
  onDeleted: () => void;
  /** „Sprawdź coś innego” w oknie potwierdzenia. */
  onCheckAnother: () => void;
}

export default function DeleteDialog({
  open,
  checkId,
  onClose,
  onDeleted,
  onCheckAnother,
}: DeleteDialogProps) {
  const [step, setStep] = useState<Step>('confirm');
  const [failed, setFailed] = useState(false);

  const onConfirm = async () => {
    setFailed(false);
    setStep('deleting');
    try {
      await deleteCheck(checkId);
      setStep('deleted');
      onDeleted();
    } catch {
      setStep('confirm');
      setFailed(true);
    }
  };

  if (step === 'deleted') {
    return (
      <Modal
        open={open}
        onClose={onClose}
        title="Twoje dane zostały usunięte"
        icon="✓"
        tone="success"
      >
        <p className="modal__text">
          Nie przechowujemy już Twojej wiadomości ani tego wyniku. Wynik widzisz jeszcze na ekranie,
          dopóki go nie zamkniesz.
        </p>
        <div className="modal__actions">
          <button
            type="button"
            className="btn-primary btn-primary--md"
            onClick={onCheckAnother}
            data-autofocus
          >
            Sprawdź coś innego
          </button>
          <button type="button" className="btn-secondary" onClick={onClose}>
            Zamknij
          </button>
        </div>
      </Modal>
    );
  }

  const deleting = step === 'deleting';

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Czy na pewno chcesz usunąć swoje dane?"
      icon="!"
      tone="danger"
      busy={deleting}
    >
      <p className="modal__text">
        Usuniemy wiadomość, którą wkleiłeś, i ten wynik. <strong>Tego nie da się cofnąć.</strong>
      </p>
      {failed && (
        <p className="field-error field-error--flat" role="alert">
          Nie udało się usunąć danych. Spróbuj jeszcze raz.
        </p>
      )}
      <div className="modal__actions">
        <button type="button" className="btn-danger" onClick={onConfirm} disabled={deleting}>
          {deleting ? 'Usuwamy…' : 'Tak, usuń moje dane'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          onClick={onClose}
          disabled={deleting}
          data-autofocus
        >
          Nie, zostaw
        </button>
      </div>
    </Modal>
  );
}
