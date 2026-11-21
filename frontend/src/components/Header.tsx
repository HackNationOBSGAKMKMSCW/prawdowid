import { useGoHome } from '../lib/navigation.ts';

interface HeaderProps {
  bigText: boolean;
  highContrast: boolean;
  onToggleBigText: () => void;
  onToggleHighContrast: () => void;
}

export default function Header({
  bigText,
  highContrast,
  onToggleBigText,
  onToggleHighContrast,
}: HeaderProps) {
  const goHome = useGoHome();

  return (
    <header className="site-header">
      <div className="site-header__stripe" />
      <div className="site-header__inner">
        <button
          type="button"
          className="brand"
          onClick={goHome}
          aria-label="Prawdowid – strona główna"
        >
          <span className="brand__flag" aria-hidden="true" />
          <span className="brand__name">Prawdowid</span>
        </button>
        <div className="view-settings" role="group" aria-label="Ustawienia wyglądu">
          <button
            type="button"
            className="pill-toggle pill-toggle--icon"
            aria-pressed={bigText}
            aria-label="Większy tekst"
            onClick={onToggleBigText}
          >
            <span className="text-size-icon" aria-hidden="true">
              <span className="text-size-icon__small">A</span>
              <span className="text-size-icon__big">A</span>
            </span>
            <span className="icon-tip" aria-hidden="true">
              {bigText ? 'Zwykły tekst' : 'Większy tekst'}
            </span>
          </button>
          <button
            type="button"
            className="pill-toggle pill-toggle--icon"
            aria-pressed={highContrast}
            aria-label="Wysoki kontrast"
            onClick={onToggleHighContrast}
          >
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
              <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.2" />
              <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" />
            </svg>
            <span className="icon-tip" aria-hidden="true">
              {highContrast ? 'Zwykły kontrast' : 'Wysoki kontrast'}
            </span>
          </button>
        </div>
      </div>
    </header>
  );
}
