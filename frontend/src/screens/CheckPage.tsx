import { useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useChecker, type Screen } from '../lib/checker.ts';
import { QUERY_PARAM } from '../lib/share.ts';
import { usePageTitle } from '../lib/usePageTitle.ts';
import CheckingScreen from './CheckingScreen.tsx';
import QuestionScreen from './QuestionScreen.tsx';
import ResultScreen from './ResultScreen.tsx';
import StartScreen from './StartScreen.tsx';
import StateScreen from './StateScreen.tsx';

const TITLES: Record<Screen['name'], string> = {
  start: 'Sprawdź wiadomość',
  checking: 'Sprawdzamy…',
  question: 'Doprecyzuj',
  result: 'Wynik',
  state: 'Komunikat',
};

/** Strona główna: formularz, sprawdzanie, wynik i komunikaty. */
export default function CheckPage() {
  const { screen, run } = useChecker();
  const [params, setParams] = useSearchParams();
  const previous = useRef<string | null>(null);

  usePageTitle(TITLES[screen.name]);

  // Link udostępniony z wyniku (`/?q=…`) od razu uruchamia sprawdzenie.
  const shared = params.get(QUERY_PARAM);
  useEffect(() => {
    if (!shared) return;
    setParams({}, { replace: true });
    run(shared);
  }, [shared, setParams, run]);

  // Każda runda pytań to osobny widok (fokus i czytanie zaczynają się od nowa).
  const view = screen.name === 'question' ? `question-${screen.round}` : screen.name;

  // Po zmianie ekranu fokus trafia na nagłówek, żeby czytnik ekranu ogłosił nowy widok.
  useEffect(() => {
    const prev = previous.current;
    previous.current = view;
    if (prev === null || prev === view) return;
    const timer = window.setTimeout(() => {
      const backToForm = view === 'start' && (prev === 'state' || prev.startsWith('question'));
      const target = document.querySelector<HTMLElement>(backToForm ? '#pw-input' : 'main h1');
      target?.focus();
      if (!backToForm) window.scrollTo(0, 0);
    }, 40);
    return () => window.clearTimeout(timer);
  }, [view]);

  switch (screen.name) {
    case 'start':
      return <StartScreen />;
    case 'checking':
      return <CheckingScreen />;
    case 'question':
      return <QuestionScreen key={screen.round} step={screen.step} round={screen.round} />;
    case 'result':
      return <ResultScreen key={screen.runId} result={screen.result} checked={screen.checked} />;
    case 'state':
      return <StateScreen kind={screen.kind} failure={screen.failure} />;
  }
}
