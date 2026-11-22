import { useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useGoHome } from '../lib/navigation.ts';
import { useSpeech } from '../lib/speech.ts';

interface HeaderProps {
  bigText: boolean;
  highContrast: boolean;
  onToggleBigText: () => void;
  onToggleHighContrast: () => void;
  dark: boolean;
  onToggleTheme: () => void;
}

export default function Header({
  bigText,
  highContrast,
  onToggleBigText,
  onToggleHighContrast,
  dark,
  onToggleTheme,
}: HeaderProps) {
  const goHome = useGoHome();
  const speech = useSpeech();
  // Dymek z podpisem da się schować klawiszem Esc (WCAG 1.4.13).
  const [tipsHidden, setTipsHidden] = useState(false);
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === 'Escape') setTipsHidden(true);
  };
  const showTips = () => setTipsHidden(false);
  const keepTip = (event: MouseEvent) => event.stopPropagation();

  return (
    <header className="site-header">
      <div className="site-header__stripe" />
      <div className="site-header__inner">
        <button
          type="button"
          className="brand"
          onClick={goHome}
          aria-label="Sprawdź.To – strona główna"
        >
          <span className="brand__flag" aria-hidden="true" />
          <span className="brand__name">Sprawdź.To</span>
        </button>
        <div
          className="view-settings"
          role="group"
          aria-label="Ułatwienia dostępu"
          data-tips-hidden={tipsHidden || undefined}
          onKeyDown={onKeyDown}
          onMouseLeave={showTips}
          onBlur={showTips}
        >
          <button
            type="button"
            className="pill-toggle pill-toggle--icon read-aloud-toggle"
            aria-pressed={speech.autoRead}
            aria-label="Czytaj stronę na głos"
            aria-describedby="read-aloud-hint"
            data-speaking={(speech.autoRead && speech.speaking) || undefined}
            onClick={speech.toggleAutoRead}
          >
            <svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true" focusable="false">
              <path
                d="M3.5 9.5h3.8L12 5.6v12.8l-4.7-3.9H3.5z"
                fill={speech.autoRead ? 'currentColor' : 'none'}
                stroke="currentColor"
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <path
                className="read-aloud-toggle__wave read-aloud-toggle__wave--near"
                d="M15.5 9.2a4 4 0 0 1 0 5.6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <path
                className="read-aloud-toggle__wave read-aloud-toggle__wave--far"
                d="M18.4 6.4a8 8 0 0 1 0 11.2"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
            <span className="icon-tip" aria-hidden="true" onClick={keepTip}>
              {speech.autoRead ? 'Wyłącz czytanie na głos' : 'Czytaj stronę na głos'}
            </span>
          </button>
          <span id="read-aloud-hint" className="sr-only">
            Syntezator mowy przeczyta treść tej strony, a potem automatycznie każdą kolejną, także
            wynik sprawdzania. Klawisz Esc przerywa czytanie. Naciśnij ponownie, aby wyłączyć.
          </span>
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
            <span className="icon-tip" aria-hidden="true" onClick={keepTip}>
              Większy tekst
            </span>
          </button>
          <button
            type="button"
            className="pill-toggle pill-toggle--icon"
            aria-pressed={dark}
            aria-label="Ciemny motyw"
            onClick={onToggleTheme}
          >
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
              <path
                d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"
                fill={dark ? 'currentColor' : 'none'}
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinejoin="round"
              />
            </svg>
            <span className="icon-tip" aria-hidden="true" onClick={keepTip}>
              Ciemny motyw
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
            <span className="icon-tip" aria-hidden="true" onClick={keepTip}>
              Wysoki kontrast
            </span>
          </button>
        </div>
      </div>
    </header>
  );
}
