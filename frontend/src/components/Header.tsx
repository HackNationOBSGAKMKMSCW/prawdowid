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
            className="pill-toggle"
            aria-pressed={bigText}
            onClick={onToggleBigText}
          >
            Większy tekst
          </button>
          <button
            type="button"
            className="pill-toggle"
            aria-pressed={highContrast}
            onClick={onToggleHighContrast}
          >
            Wysoki kontrast
          </button>
        </div>
      </div>
    </header>
  );
}
