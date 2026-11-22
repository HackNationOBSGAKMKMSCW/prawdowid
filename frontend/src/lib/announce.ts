import { createContext, useContext } from 'react';

export type Announce = (message: string) => void;

export const AnnouncerContext = createContext<Announce>(() => {});

/** Odczytuje komunikat czytnikom ekranu (`aria-live="polite"`). */
export function useAnnounce(): Announce {
  return useContext(AnnouncerContext);
}
