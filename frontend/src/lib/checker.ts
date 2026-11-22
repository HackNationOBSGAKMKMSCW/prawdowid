import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { checkMessage, clarifyMessage } from '../api/client.ts';
import type { Scenario } from '../api/mock.ts';
import type { CheckResult, ClarifyStep, ClarifyTurn } from '../api/types.ts';

export type StateKind = 'clarify' | 'out_of_scope' | 'failure';

export type Screen =
  | { name: 'start' }
  | { name: 'checking' }
  /** Dopytujemy o szczegóły (kiedy, gdzie…), zanim sprawdzimy wiadomość. */
  | { name: 'question'; step: ClarifyStep; round: number }
  /** `checked` – twierdzenie z odpowiedziami użytkownika, gdy dopytywaliśmy. */
  | { name: 'result'; result: CheckResult; runId: number; checked?: string }
  | { name: 'state'; kind: StateKind };

export interface Checker {
  screen: Screen;
  input: string;
  setInput: (value: string) => void;
  /** Pusta wiadomość przy próbie sprawdzenia. */
  error: boolean;
  /** Sprawdza `text` (domyślnie bieżącą treść pola). Najpierw może dopytać o szczegóły. */
  run: (text?: string, scenario?: Scenario) => void;
  /** Odpowiedź na pytania doprecyzowujące. */
  answer: (text: string) => void;
  /** Sprawdza bez odpowiadania na pytania (z tym, co już wiemy). */
  skipQuestions: () => void;
  /** Ponawia ostatnie sprawdzenie po błędzie. */
  retry: () => void;
  /** Wraca do formularza; `clear` czyści pole. */
  goStart: (clear: boolean) => void;
}

/**
 * Stan sprawdzania wiadomości: start → (pytania o szczegóły) → sprawdzanie → wynik albo komunikat.
 *
 * Krótka wiadomość o konkretnym zdarzeniu („Czy spadł dron w Polsce?”) najpierw trafia do
 * `/api/clarify`. Gdy brakuje szczegółów, pokazujemy pytania; odpowiedzi łączą się z
 * pierwszą wiadomością w jedno twierdzenie, które sprawdza `/api/check`. Ta sama pętla
 * działa w bocie WhatsApp.
 */
export function useCheckerState(): Checker {
  const [screen, setScreen] = useState<Screen>({ name: 'start' });
  const [input, setInputValue] = useState('');
  const [error, setError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const lastScenario = useRef<Scenario | undefined>(undefined);
  const lastChecked = useRef<{ text: string; withDetails: boolean } | null>(null);
  const runCounter = useRef(0);

  const abort = useCallback(() => {
    controller.current?.abort();
    controller.current = null;
  }, []);

  useEffect(() => abort, [abort]);

  const setInput = useCallback((value: string) => {
    setInputValue(value);
    setError(false);
  }, []);

  /** Nowe zapytanie: przerywa poprzednie i pokazuje „Sprawdzamy…”. */
  const begin = useCallback(() => {
    abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setError(false);
    setScreen({ name: 'checking' });
    return ctrl;
  }, [abort]);

  const check = useCallback(
    (text: string, withDetails: boolean, scenario?: Scenario) => {
      const ctrl = begin();
      const runId = ++runCounter.current;
      lastScenario.current = scenario;
      lastChecked.current = { text, withDetails };

      checkMessage(text, { signal: ctrl.signal, scenario }).then(
        (response) => {
          if (ctrl.signal.aborted) return;
          if (response.status === 'result')
            setScreen({
              name: 'result',
              result: response,
              runId,
              checked: withDetails ? text : undefined,
            });
          else setScreen({ name: 'state', kind: response.status });
        },
        () => {
          if (ctrl.signal.aborted) return;
          setScreen({ name: 'state', kind: 'failure' });
        },
      );
    },
    [begin],
  );

  /** Jeden krok pętli doprecyzowania; błąd nigdy nie blokuje sprawdzenia. */
  const clarify = useCallback(
    (turns: ClarifyTurn[], fallback: () => { text: string; withDetails: boolean }) => {
      const ctrl = begin();
      clarifyMessage(turns, { signal: ctrl.signal }).then(
        (step) => {
          if (ctrl.signal.aborted) return;
          if (step.new_topic) {
            const first = step.turns.find((t) => t.role === 'user');
            if (first) setInputValue(first.text);
          }
          if (step.status === 'ask') {
            const round = step.turns.filter((t) => t.role === 'bot').length;
            setScreen({ name: 'question', step, round });
          } else if (step.status === 'too_short') {
            setScreen({ name: 'state', kind: 'clarify' });
          } else {
            check(step.claim, step.with_details);
          }
        },
        () => {
          if (ctrl.signal.aborted) return;
          const { text, withDetails } = fallback();
          check(text, withDetails);
        },
      );
    },
    [begin, check],
  );

  const run = useCallback(
    (text?: string, scenario?: Scenario) => {
      const value = (text ?? input).trim();
      if (!value) {
        setError(true);
        return;
      }
      setInputValue(value);
      // Przykłady z paska demo pokazują gotowy scenariusz, bez dopytywania.
      if (scenario) {
        check(value, false, scenario);
        return;
      }
      clarify([{ role: 'user', text: value }], () => ({ text: value, withDetails: false }));
    },
    [input, check, clarify],
  );

  const answer = useCallback(
    (text: string) => {
      if (screen.name !== 'question') return;
      const value = text.trim();
      if (!value) return;
      const { step } = screen;
      const turns: ClarifyTurn[] = [...step.turns, { role: 'user', text: value }];
      // Bez odpowiedzi serwera łączymy wiadomość z odpowiedziami sami.
      const fallback = () => {
        const [first, ...answers] = turns.filter((t) => t.role === 'user').map((t) => t.text);
        return {
          text: `${first} (szczegóły od użytkownika: ${answers.join('; ')})`,
          withDetails: true,
        };
      };
      clarify(turns, fallback);
    },
    [screen, clarify],
  );

  const skipQuestions = useCallback(() => {
    if (screen.name !== 'question') return;
    const { step } = screen;
    const answered = step.turns.filter((t) => t.role === 'user').length > 1;
    check(step.skip_claim, answered);
  }, [screen, check]);

  const retry = useCallback(() => {
    const last = lastChecked.current;
    if (!last) {
      run(input);
      return;
    }
    // Awaria z paska demo jest symulowana – ponowienie pokazuje zwykły wynik.
    const scenario = lastScenario.current === 'failure' ? 'generic' : lastScenario.current;
    check(last.text, last.withDetails, scenario);
  }, [run, check, input]);

  const goStart = useCallback(
    (clear: boolean) => {
      abort();
      if (clear) setInputValue('');
      setError(false);
      setScreen({ name: 'start' });
    },
    [abort],
  );

  return { screen, input, setInput, error, run, answer, skipQuestions, retry, goStart };
}

export const CheckerContext = createContext<Checker | null>(null);

export function useChecker(): Checker {
  const checker = useContext(CheckerContext);
  if (!checker) throw new Error('useChecker musi być użyty wewnątrz CheckerContext.Provider');
  return checker;
}
