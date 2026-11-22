import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { useAnnounce } from './announce.ts';
import { useChecker } from './checker.ts';
import { SpeechContext, type Speech, type SpeechBlock, type SpeechContent } from './speech.ts';

const MAX_CHUNK = 220;
/** Opóźnienie po zmianie ekranu: fokus, tytuł i treść zdążą się ustawić. */
const AUTO_READ_DELAY = 450;
/** Cisza po akapicie, punkcie listy, przycisku (ms). */
const BLOCK_PAUSE = 650;
/** Cisza po nagłówku (ms). */
const HEADING_PAUSE = 1000;
/** Cisza między zdaniami jednego długiego bloku (ms). */
const SENTENCE_PAUSE = 200;

const HEADING = 'h1, h2, h3, h4, h5, h6';
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
 * Najbliższy przodek wyświetlany jako blok (akapit, punkt listy, przycisk,
 * link-kafelek…). Tekst w elementach liniowych (`strong`, link w zdaniu)
 * zostaje w bloku rodzica, więc zdanie nie rwie się w połowie.
 */
function blockOf(element: Element, root: Element): Element {
  for (let el: Element | null = element; el && el !== root; el = el.parentElement) {
    const display = getComputedStyle(el).display;
    if (display !== 'inline' && display !== 'contents') return el;
  }
  return root;
}

/**
 * Widoczna treść `<main>` podzielona na bloki (nagłówek, akapit, punkt listy,
 * przycisk). Pomija elementy ukryte, pola formularza i okna.
 */
function mainBlocks(): SpeechBlock[] {
  const main = document.getElementById('tresc');
  if (!main) return [];
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  const blocks: SpeechBlock[] = [];
  let text = '';
  let block: Element | null = null;
  let lastParent: Element | null = null;
  const flush = () => {
    const value = text.replace(/\s+/g, ' ').trim();
    if (value) blocks.push({ text: value, heading: !!block?.closest(HEADING) });
    text = '';
  };
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const value = node.nodeValue?.replace(/\s+/g, ' ');
    const parent = node.parentElement;
    if (!value || !parent || parent.closest(SKIP)) continue;
    if (parent.checkVisibility && !parent.checkVisibility()) continue;
    if (!value.trim()) {
      // Sama spacja między elementami („Potwierdzone –{' '}opis”) też rozdziela słowa.
      if (text && !/\s$/.test(text)) text += ' ';
      continue;
    }
    const nextBlock = blockOf(parent, main);
    if (nextBlock !== block) {
      flush();
      block = nextBlock;
    } else if (parent !== lastParent && text && !/\s$/.test(text) && !/^[\s.,;:!?…)]/.test(value)) {
      // Sąsiednie elementy w jednej linii („gov.pl” obok nazwy grupy) – rozdziel spacją.
      text += ' ';
    }
    lastParent = parent;
    text += value;
  }
  flush();
  return blocks;
}

interface Part {
  text: string;
  /** Cisza po tym fragmencie (ms). */
  pause: number;
}

/**
 * Zamienia treść na kolejkę krótkich wypowiedzi z pauzami. Każdy blok kończy
 * się kropką (opadająca intonacja), a po nim jest cisza – dłuższa po nagłówku.
 */
function toParts(content: SpeechContent): Part[] {
  const blocks = typeof content === 'string' ? [content] : content;
  const parts: Part[] = [];
  for (const item of blocks) {
    const block = typeof item === 'string' ? { text: item } : item;
    const text = block.text.replace(/\s+/g, ' ').trim();
    if (!text) continue;
    const sentences = chunks(/[.!?…:;”"]$/.test(text) ? text : `${text}.`);
    sentences.forEach((sentence, i) => {
      const last = i === sentences.length - 1;
      parts.push({
        text: sentence,
        pause: !last ? SENTENCE_PAUSE : block.heading ? HEADING_PAUSE : BLOCK_PAUSE,
      });
    });
  }
  return parts;
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
  const [pending, setPending] = useState<SpeechContent | null>(null);
  const pageText = useRef<SpeechContent | null>(null);
  // Pauza między blokami i bieżąca wypowiedź (Chrome gubi `onend`, gdy obiekt zniknie z pamięci).
  const pauseTimer = useRef<number | undefined>(undefined);
  const current = useRef<SpeechSynthesisUtterance | null>(null);
  // Włączenie przyciskiem czyta od razu, więc efekt nie zaczyna drugi raz.
  const justEnabled = useRef(false);

  const stop = useCallback(() => {
    generation.current += 1;
    window.clearTimeout(pauseTimer.current);
    current.current = null;
    setPending(null);
    synth()?.cancel();
    setSpeaking(false);
  }, []);

  const speak = useCallback(
    (content: SpeechContent) => {
      const engine = synth();
      if (!engine || typeof SpeechSynthesisUtterance === 'undefined') {
        announce('Twoja przeglądarka nie umie czytać na głos.');
        return;
      }
      const gen = ++generation.current;
      window.clearTimeout(pauseTimer.current);
      engine.cancel();
      setPending(null);
      const parts = toParts(content);
      if (!parts.length) {
        setSpeaking(false);
        return;
      }
      const voice = polishVoice();

      // Fragmenty idą po kolei: kolejny startuje dopiero po ciszy po poprzednim.
      const play = (i: number) => {
        if (generation.current !== gen) return;
        const part = parts[i];
        const utterance = new SpeechSynthesisUtterance(part.text);
        utterance.lang = 'pl-PL';
        if (voice) utterance.voice = voice;
        utterance.rate = 0.95;
        utterance.onend = () => {
          if (generation.current !== gen) return;
          if (i === parts.length - 1) {
            current.current = null;
            setSpeaking(false);
            return;
          }
          pauseTimer.current = window.setTimeout(() => play(i + 1), part.pause);
        };
        utterance.onerror = (event) => {
          if (generation.current !== gen) return;
          if (event.error === 'interrupted' || event.error === 'canceled') return;
          generation.current += 1;
          current.current = null;
          setSpeaking(false);
          if (event.error === 'not-allowed') setPending(content);
        };
        current.current = utterance;
        engine.speak(utterance);
      };

      play(0);
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
      const content = pageText.current ?? mainBlocks();
      if (content.length) speak(content);
    }, AUTO_READ_DELAY);
    return () => window.clearTimeout(timer);
  }, [view, autoRead, speak, stop]);

  const setPageText = useCallback((content: SpeechContent | null) => {
    pageText.current = content;
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
      speak(pageText.current ?? mainBlocks());
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
