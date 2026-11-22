import { createContext, useContext, useEffect } from 'react';

/** Fragment czytany osobno; po nim syntezator robi wyraźną pauzę. */
export interface SpeechBlock {
  text: string;
  /** Nagłówek – po nim pauza jest dłuższa. */
  heading?: boolean;
}

/** Tekst do czytania: jeden ciąg albo lista bloków (akapitów, nagłówków, punktów). */
export type SpeechContent = string | (string | SpeechBlock)[];

export interface Speech {
  /** Czy przeglądarka ma syntezator mowy (Web Speech API). */
  supported: boolean;
  /** Czy właśnie coś czytamy. */
  speaking: boolean;
  /** Czytanie każdej strony na głos (przełącznik w nagłówku). */
  autoRead: boolean;
  /** Włącza lub wyłącza czytanie każdej strony; po włączeniu od razu czyta bieżącą. */
  toggleAutoRead: () => void;
  /** Czyta tekst od początku, przerywając poprzednie czytanie. */
  speak: (content: SpeechContent) => void;
  /** Przerywa czytanie. */
  stop: () => void;
  /**
   * Tekst, który ekran chce mieć przeczytany zamiast treści strony
   * (np. wynik sprawdzania). `null` = czytaj treść z `<main>`.
   */
  setPageText: (content: SpeechContent | null) => void;
}

export const SpeechContext = createContext<Speech>({
  supported: false,
  speaking: false,
  autoRead: false,
  toggleAutoRead: () => {},
  speak: () => {},
  stop: () => {},
  setPageText: () => {},
});

/** Czytanie na głos: wspólny syntezator dla nagłówka i ekranów. */
export function useSpeech(): Speech {
  return useContext(SpeechContext);
}

/**
 * Ekran podaje gotowy tekst do automatycznego czytania (zamiast całej treści
 * strony z przyciskami). Tekst znika, gdy ekran się odmontuje.
 */
export function usePageSpeechText(text: SpeechContent) {
  const { setPageText } = useSpeech();
  useEffect(() => {
    setPageText(text);
    return () => setPageText(null);
  }, [text, setPageText]);
}
