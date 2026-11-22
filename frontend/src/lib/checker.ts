import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { checkMessage } from '../api/client.ts';
import type { Scenario } from '../api/mock.ts';
import type { CheckResult } from '../api/types.ts';

export type StateKind = 'clarify' | 'out_of_scope' | 'failure';

export type Screen =
  | { name: 'start' }
  | { name: 'checking' }
  | { name: 'result'; result: CheckResult; runId: number }
  | { name: 'state'; kind: StateKind };

export interface Checker {
  screen: Screen;
  input: string;
  setInput: (value: string) => void;
  /** Pusta wiadomość przy próbie sprawdzenia. */
  error: boolean;
  /** Sprawdza `text` (domyślnie bieżącą treść pola). */
  run: (text?: string, scenario?: Scenario) => void;
  /** Ponawia ostatnie sprawdzenie po błędzie. */
  retry: () => void;
  /** Wraca do formularza; `clear` czyści pole. */
  goStart: (clear: boolean) => void;
}

/** Stan sprawdzania wiadomości: ekran startowy → sprawdzanie → wynik albo komunikat. */
export function useCheckerState(): Checker {
  const [screen, setScreen] = useState<Screen>({ name: 'start' });
  const [input, setInputValue] = useState('');
  const [error, setError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  const lastScenario = useRef<Scenario | undefined>(undefined);
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

  const run = useCallback(
    (text?: string, scenario?: Scenario) => {
      const value = (text ?? input).trim();
      if (!value) {
        setError(true);
        return;
      }
      abort();
      const ctrl = new AbortController();
      const runId = ++runCounter.current;
      controller.current = ctrl;
      lastScenario.current = scenario;
      setInputValue(value);
      setError(false);
      setScreen({ name: 'checking' });

      checkMessage(value, { signal: ctrl.signal, scenario }).then(
        (response) => {
          if (ctrl.signal.aborted) return;
          if (response.status === 'result') setScreen({ name: 'result', result: response, runId });
          else setScreen({ name: 'state', kind: response.status });
        },
        () => {
          if (ctrl.signal.aborted) return;
          setScreen({ name: 'state', kind: 'failure' });
        },
      );
    },
    [input, abort],
  );

  const retry = useCallback(() => {
    // Awaria z paska demo jest symulowana – ponowienie pokazuje zwykły wynik.
    const scenario = lastScenario.current === 'failure' ? 'generic' : lastScenario.current;
    run(input, scenario);
  }, [run, input]);

  const goStart = useCallback(
    (clear: boolean) => {
      abort();
      if (clear) setInputValue('');
      setError(false);
      setScreen({ name: 'start' });
    },
    [abort],
  );

  return { screen, input, setInput, error, run, retry, goStart };
}

export const CheckerContext = createContext<Checker | null>(null);

export function useChecker(): Checker {
  const checker = useContext(CheckerContext);
  if (!checker) throw new Error('useChecker musi być użyty wewnątrz CheckerContext.Provider');
  return checker;
}
