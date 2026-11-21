import { useCallback, type MouseEvent } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useChecker } from './checker.ts';

/** Powrót do pustego formularza na stronie głównej. */
export function useGoHome() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { goStart } = useChecker();
  return useCallback(() => {
    goStart(true);
    if (pathname !== '/') navigate('/');
  }, [goStart, navigate, pathname]);
}

function focusSection(id: string) {
  const el = document.getElementById(id);
  if (!el) return;
  window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 16);
  el.setAttribute('tabindex', '-1');
  el.focus({ preventScroll: true });
}

/**
 * Przejście do sekcji strony startowej („Jak to działa”, „Lista źródeł”) z
 * dowolnego miejsca aplikacji: z wyniku, komunikatu albo podstrony.
 */
export function useGoToSection() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { screen, goStart } = useChecker();
  return useCallback(
    (event: MouseEvent<HTMLAnchorElement>, id: string) => {
      if (pathname === '/' && screen.name === 'start') {
        event.preventDefault();
        focusSection(id);
        return;
      }
      event.preventDefault();
      goStart(true);
      if (pathname !== '/') navigate('/');
      window.setTimeout(() => focusSection(id), 80);
    },
    [pathname, screen.name, goStart, navigate],
  );
}
