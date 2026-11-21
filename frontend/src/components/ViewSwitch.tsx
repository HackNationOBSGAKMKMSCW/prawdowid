import { NavLink, useLocation } from 'react-router-dom';

/** Przełącznik między dwoma widokami aplikacji: stroną i czatem WhatsApp. */
export default function ViewSwitch() {
  const { pathname } = useLocation();
  const onWhatsApp = pathname.startsWith('/whatsapp');

  return (
    <nav className="view-switch" aria-label="Widok aplikacji">
      <div className="view-switch__tabs">
        <NavLink
          to="/"
          className="view-switch__tab"
          aria-current={onWhatsApp ? undefined : 'page'}
          data-active={!onWhatsApp}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
            <path
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              d="M3 6.5A2.5 2.5 0 0 1 5.5 4h13A2.5 2.5 0 0 1 21 6.5v11a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5zM3 9h18"
            />
          </svg>
          Strona
        </NavLink>
        <NavLink to="/whatsapp" className="view-switch__tab" data-active={onWhatsApp}>
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
            <path
              fill="currentColor"
              d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2Zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2Z"
            />
          </svg>
          WhatsApp
        </NavLink>
      </div>
    </nav>
  );
}
