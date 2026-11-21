import { useEffect, useId, useRef, type ReactNode } from 'react';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Znak w kółku nad tytułem (dekoracyjny). */
  icon?: string;
  tone?: 'info' | 'warning' | 'danger' | 'success';
  /** Blokuje zamykanie (np. w trakcie wysyłania). */
  busy?: boolean;
  /** Szersze okno na dłuższe treści informacyjne. */
  wide?: boolean;
  children: ReactNode;
}

/**
 * Okno modalne na natywnym `<dialog>`: przeglądarka sama zatrzymuje fokus w
 * oknie, zamyka je klawiszem Esc i oddaje fokus przyciskowi, który je otworzył.
 */
export default function Modal({
  open,
  onClose,
  title,
  icon,
  tone = 'info',
  busy,
  wide,
  children,
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      // Przycisk oznaczony `data-autofocus` dostaje fokus zamiast pierwszego w oknie.
      dialog.querySelector<HTMLElement>('[data-autofocus]')?.focus();
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  // Zmiana kroku w otwartym oknie (np. „Dziękujemy”) przenosi fokus na jego główny przycisk.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog?.open) return;
    dialog.scrollTop = 0;
    const target =
      dialog.querySelector<HTMLElement>('[data-autofocus]') ??
      dialog.querySelector<HTMLElement>('.modal__title');
    target?.focus();
  }, [title]);

  return (
    <dialog
      ref={ref}
      className={wide ? 'modal modal--wide' : 'modal'}
      aria-labelledby={titleId}
      onKeyDown={(e) => {
        // Tab i Shift+Tab krążą tylko po elementach okna.
        if (e.key !== 'Tab') return;
        const focusable = [
          ...e.currentTarget.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
          ),
        ].filter((el) => el.offsetParent !== null);
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && (active === first || !e.currentTarget.contains(active))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      onClick={(e) => {
        // Kliknięcie w przyciemnione tło zamyka okno.
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div className="modal__box">
        <button
          type="button"
          className="modal__close"
          onClick={onClose}
          disabled={busy}
          aria-label="Zamknij okno"
        >
          <span aria-hidden="true">✕</span>
        </button>
        {icon && (
          <span className="modal__icon" data-tone={tone} aria-hidden="true">
            {icon}
          </span>
        )}
        <h2 id={titleId} className="modal__title" tabIndex={-1}>
          {title}
        </h2>
        {children}
      </div>
    </dialog>
  );
}
