import { useCallback, useState, type ReactNode } from 'react';
import { AnnouncerContext, type Announce } from './announce.ts';

/**
 * Region `aria-live`, przez który komunikaty („Link skopiowany.”) trafiają do
 * czytników ekranu bez przenoszenia fokusu.
 */
export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState('');

  const announce = useCallback<Announce>((next) => {
    // Wyczyszczenie przed ustawieniem sprawia, że ten sam komunikat zostanie przeczytany ponownie.
    setMessage('');
    window.setTimeout(() => setMessage(next), 50);
  }, []);

  return (
    <AnnouncerContext.Provider value={announce}>
      {children}
      <div role="status" aria-live="polite" className="sr-only">
        {message}
      </div>
    </AnnouncerContext.Provider>
  );
}
