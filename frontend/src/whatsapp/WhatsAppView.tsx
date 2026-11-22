import ViewSwitch from '../components/ViewSwitch.tsx';
import { usePageTitle } from '../lib/usePageTitle.ts';
import WhatsAppSimulator from './WhatsAppSimulator.tsx';

/** Drugi widok aplikacji: symulator czatu WhatsApp ze Sprawdź.To. */
export default function WhatsAppView() {
  usePageTitle('WhatsApp');

  return (
    <div className="wa-view">
      <main aria-labelledby="wa-view-title">
        <h1 id="wa-view-title" className="sr-only">
          Demo WhatsApp: czat ze Sprawdź.To
        </h1>
        <WhatsAppSimulator />
      </main>
      <ViewSwitch />
    </div>
  );
}
