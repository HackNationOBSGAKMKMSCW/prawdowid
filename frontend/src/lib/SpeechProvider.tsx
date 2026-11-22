import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnounce } from './announce.ts';
import { useChecker } from './checker.ts';
import { SpeechContext, type Speech } from './speech.ts';

const MAX_CHUNK = 220;
/** Opóźnienie po zmianie ekranu: fokus, tytuł i treść zdążą się ustawić. */
const AUTO_READ_DELAY = 450;

const BLOCK =
  'h1, h2, h3, h4, h5, h6, p, li, dt, dd, label, legend, blockquote, figcaption, summary, th, td, button, div, section, article';
const SKIP =
  '[aria-hidden="true"], [hidden], a .sr-only, dialog, textarea, input, select, script, style, [data-speech-skip]';

function synth(): SpeechSynthesis | undefined {
  return typeof window !== 'undefined' ? window.speechSynthesis : undefined;
}

function polishVoice(): SpeechSynthesisVoice | undefined {
  const voices = synth()?.getVoices() ?? [];
  return (
    voices.find((v) => v.lang.toLowerCase() === 'pl-pl') ??
    voices.find((v) => v.lang.toLowerCase().startsWith('pl'))
  );
}

/**
 * Dzieli tekst na krótkie kawałki po zdaniach. Chrome przerywa długie
 * wypowiedzi po kilkunastu sekundach, a krótkie czyta bez zacięć.
 */
function chunks(text: string): string[] {
  const sentences = text
    .replace(/\s+/g, ' ')
    .trim()
    .split(/(?<=[.!?…:;])\s+/);
  const out: string[] = [];
  let current = '';
  for (const sentence of sentences) {
    if (!sentence) continue;
    if (sentence.length > MAX_CHUNK) {
      if (current) out.push(current);
      current = '';
      // Bardzo długie zdanie dzielimy po przecinkach, a w ostateczności po słowach.
      let rest = sentence;
      while (rest.length > MAX_CHUNK) {
        const cut = Math.max(rest.lastIndexOf(', ', MAX_CHUNK), rest.lastIndexOf(' ', MAX_CHUNK));
        const at = cut > 0 ? cut + 1 : MAX_CHUNK;
        out.push(rest.slice(0, at).trim());
        rest = rest.slice(at).trim();
      }
      if (rest) current = rest;
      continue;
    }
    if (current && current.length + sentence.length + 1 > MAX_CHUNK) {
      out.push(current);
      current = sentence;
    } else {
      current = current ? `${current} ${sentence}` : sentence;
    }
  }
  if (current) out.push(current);
  return out;
}

/**
 * Widoczna treść `<main>` jako tekst do czytania. Pomija elementy ukryte,
 * pola formularza i okna; między blokami (nagłówek, akapit, punkt listy)
 * wstawia kropkę, żeby syntezator zrobił pauzę.
 */
function mainText(): string {
  const main = document.getElementById('tresc');
  if (!main) return '';
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  const parts: string[] = [];
  let lastBlock: Element | null = null;
  let lastParent: Element | null = null;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const value = node.nodeValue?.replace(/\s+/g, ' ');
    const parent = node.parentElement;
    if (!value || !parent || parent.closest(SKIP)) continue;
    if (parent.checkVisibility && !parent.checkVisibility()) continue;
    if (!value.trim()) {
      // Sama spacja między elementami („Potwierdzone –{' '}opis”) też rozdziela słowa.
      if (parts.length && !/\s$/.test(parts[parts.length - 1])) parts.push(' ');
      continue;
    }
    const block = parent.closest(BLOCK);
    const prev = parts.length ? parts[parts.length - 1] : '';
    if (prev && block !== lastBlock) {
      const trimmed = prev.trimEnd();
      parts[parts.length - 1] = /[.!?…:;,]$/.test(trimmed) ? `${trimmed} ` : `${trimmed}. `;
    } else if (prev && parent !== lastParent && !/\s$/.test(prev) && !/^[\s.,;:!?…)]/.test(value)) {
      // Sąsiednie elementy w jednej linii („gov.pl” obok nazwy grupy) – rozdziel spacją.
      parts[parts.length - 1] = `${prev} `;
    }
    lastBlock = block;
    lastParent = parent;
    parts.push(value);
  }
  return parts.join('').replace(/\s+/g, ' ').trim();
}

interface SpeechProviderProps {
  autoRead: boolean;
  onToggleAutoRead: () => void;
  children: ReactNode;
}

/**
 * Syntezator mowy przeglądarki wspólny dla całej strony. Gdy czytanie jest
 * włączone w nagłówku, każda nowa strona i każdy nowy ekran (np. wynik
 * sprawdzania) jest czytany automatycznie.
 */
export function SpeechProvider({ autoRead, onToggleAutoRead, children }: SpeechProviderProps) {
  const announce = useAnnounce();
  const { pathname } = useLocation();
  const { screen } = useChecker();
  const [speaking, setSpeaking] = useState(false);
  const supported = !!synth() && typeof SpeechSynthesisUtterance !== 'undefined';

  // Każde nowe czytanie dostaje numer; zdarzenia starszych wypowiedzi są ignorowane.
  const generation = useRef(0);
  // Tekst czekający na pierwszy gest użytkownika (przeglądarka blokuje mowę bez niego).
  const [pending, setPending] = useState<string | null>(null);
  const pageText = useRef<string | null>(null);
  // Włączenie przyciskiem czyta od razu, więc efekt nie zaczyna drugi raz.
  const justEnabled = useRef(false);

  const stop = useCallback(() => {
    generation.current += 1;
    setPending(null);
    synth()?.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (text: string) => {
      const engine = synth();
      if (!engine || typeof SpeechSynthesisUtterance === 'undefined') {
        announce('Twoja przeglądarka nie umie czytać na głos.');
        return;
      }
      const gen = ++generation.current;
      engine.cancel();
      setPending(null);
      const parts = chunks(text);
      if (!parts.length) {
        setSpeaking(false);
        return;
      }
      const voice = polishVoice();
      parts.forEach((part, i) => {
        const utterance = new SpeechSynthesisUtterance(part);
        utterance.lang = 'pl-PL';
        if (voice) utterance.voice = voice;
        utterance.rate = 0.95;
        if (i === parts.length - 1) {
          utterance.onend = () => {
            if (generation.current === gen) setSpeaking(false);
          };
        }
        utterance.onerror = (event) => {
          if (generation.current !== gen) return;
          if (event.error === 'interrupted' || event.error === 'canceled') return;
          generation.current += 1;
          setSpeaking(false);
          if (event.error === 'not-allowed') setPending(text);
        };
        engine.speak(utterance);
      });
      setSpeaking(true);
    },
    [announce],
  );

  // Po odświeżeniu strony przeglądarka nie pozwala mówić, dopóki użytkownik
  // czegoś nie kliknie lub nie naciśnie klawisza – wtedy zaczynamy czytać.
  useEffect(() => {
    if (!pending) return;
    const resume = () => speak(pending);
    const events = ['pointerup', 'keydown', 'touchend'] as const;
    events.forEach((name) => window.addEventListener(name, resume, { capture: true, once: true }));
    return () => events.forEach((name) => window.removeEventListener(name, resume, true));
  }, [pending, speak]);

  // Esc przerywa czytanie (czytanie automatyczne zostaje włączone).
  useEffect(() => {
    if (!speaking) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') stop();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [speaking, stop]);

  // Klucz bieżącego widoku: inna strona albo inny ekran sprawdzania.
  const view = `${pathname}|${screen.name}|${screen.name === 'result' ? screen.runId : ''}`;

  // Zmiana strony lub ekranu przerywa czytanie poprzedniej treści.
  useEffect(() => () => stop(), [view, stop]);

  useEffect(() => {
    if (!autoRead) return;
    if (justEnabled.current) {
      justEnabled.current = false;
      return;
    }
    const timer = window.setTimeout(() => {
      const text = pageText.current ?? mainText();
      if (text) speak(text);
    }, AUTO_READ_DELAY);
    return () => window.clearTimeout(timer);
  }, [view, autoRead, speak, stop]);

  const setPageText = useCallback((text: string | null) => {
    pageText.current = text;
  }, []);

  // Mowa startuje jeszcze w obsłudze kliknięcia – Safari na iPhonie wymaga,
  // żeby pierwsze czytanie zaczęło się od gestu użytkownika.
  const toggleAutoRead = useCallback(() => {
    if (!autoRead) {
      if (!supported) {
        announce('Twoja przeglądarka nie umie czytać na głos.');
        return;
      }
      justEnabled.current = true;
      speak(pageText.current ?? mainText());
    } else {
      stop();
    }
    onToggleAutoRead();
  }, [autoRead, supported, announce, speak, stop, onToggleAutoRead]);

  const value = useMemo<Speech>(
    () => ({ supported, speaking, autoRead, toggleAutoRead, speak, stop, setPageText }),
    [supported, speaking, autoRead, toggleAutoRead, speak, stop, setPageText],
  );

  return <SpeechContext.Provider value={value}>{children}</SpeechContext.Provider>;
}
