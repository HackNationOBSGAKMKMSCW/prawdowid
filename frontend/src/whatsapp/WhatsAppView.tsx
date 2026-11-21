import ViewSwitch from '../components/ViewSwitch.tsx';
import { usePageTitle } from '../lib/usePageTitle.ts';
import WhatsAppSimulator from './WhatsAppSimulator.tsx';

/** Drugi widok aplikacji: symulator czatu WhatsApp z Prawdowidem. */
export default function WhatsAppView() {
  usePageTitle('WhatsApp');

  return (
    <div className="wa-view">
      <ViewSwitch />
      <WhatsAppSimulator />
    </div>
  );
}
