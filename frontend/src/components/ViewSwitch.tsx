import { Link, useLocation } from 'react-router-dom';

/**
 * Dyskretny przycisk w prawym dolnym rogu: przełącza między stroną a demo
 * czatu WhatsApp. Pełny opis pokazuje się po najechaniu albo fokusie.
 */
export default function ViewSwitch() {
  const { pathname } = useLocation();
  const onWhatsApp = pathname.startsWith('/whatsapp');

  const to = onWhatsApp ? '/' : '/whatsapp';
  const label = onWhatsApp ? 'Wróć do strony Prawdowid' : 'Przełącz na demo WhatsApp';
  const short = onWhatsApp ? 'Strona' : 'Demo WhatsApp';

  return (
    <Link
      to={to}
      viewTransition
      className="view-switch"
      data-target={onWhatsApp ? 'web' : 'whatsapp'}
      aria-label={label}
    >
      <span className="view-switch__icon" aria-hidden="true">
        {onWhatsApp ? (
          <svg viewBox="0 0 24 24" width="20" height="20" focusable="false">
            <path
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 6.5A2.5 2.5 0 0 1 5.5 4h13A2.5 2.5 0 0 1 21 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5zM3 9h18"
            />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="20" height="20" focusable="false">
            <path
              fill="currentColor"
              d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Z"
            />
          </svg>
        )}
      </span>
      <span className="view-switch__text">
        <span className="view-switch__tag">Demo</span>
        <span className="view-switch__long">{label}</span>
        <span className="view-switch__short" aria-hidden="true">
          {short}
        </span>
      </span>
    </Link>
  );
}
