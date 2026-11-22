import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useChecker, type Screen } from '../lib/checker.ts';
import { QUERY_PARAM } from '../lib/share.ts';
import { usePageTitle } from '../lib/usePageTitle.ts';
import CheckingScreen from './CheckingScreen.tsx';
import ResultScreen from './ResultScreen.tsx';
import StartScreen from './StartScreen.tsx';
import StateScreen from './StateScreen.tsx';

const TITLES: Record<Screen['name'], string> = {
  start: 'Sprawdź wiadomość',
  checking: 'Sprawdzamy…',
  result: 'Wynik',
  state: 'Komunikat',
};

/** Strona główna: formularz, sprawdzanie, wynik i komunikaty. */
export default function CheckPage() {
  const { screen, run } = useChecker();
  const [params, setParams] = useSearchParams();
  const previous = useRef<Screen['name'] | null>(null);

  usePageTitle(TITLES[screen.name]);

  // Link udostępniony z wyniku (`/?q=…`) od razu uruchamia sprawdzenie.
  const shared = params.get(QUERY_PARAM);
  useEffect(() => {
    if (!shared) return;
    setParams({}, { replace: true });
    run(shared);
  }, [shared, setParams, run]);

  // Po zmianie ekranu fokus trafia na nagłówek, żeby czytnik ekranu ogłosił nowy widok.
  useEffect(() => {
    const prev = previous.current;
    previous.current = screen.name;
    if (prev === null || prev === screen.name) return;
    const timer = window.setTimeout(() => {
      const backToForm = screen.name === 'start' && prev === 'state';
      const target = document.querySelector<HTMLElement>(backToForm ? '#pw-input' : 'main h1');
      target?.focus();
      if (!backToForm) window.scrollTo(0, 0);
    }, 40);
    return () => window.clearTimeout(timer);
  }, [screen.name]);

  switch (screen.name) {
    case 'start':
      return <StartScreen />;
    case 'checking':
      return <CheckingScreen />;
    case 'result':
      return <ResultScreen key={screen.runId} result={screen.result} />;
    case 'state':
      return <StateScreen kind={screen.kind} failure={screen.failure} />;
  }
}
