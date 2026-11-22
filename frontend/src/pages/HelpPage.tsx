import { HelpContent } from '../components/InfoSections.tsx';
import InfoPage from './InfoPage.tsx';

export default function HelpPage() {
  return (
    <InfoPage title="Pomoc" lead="Odpowiedzi na najczęstsze pytania.">
      <HelpContent />
    </InfoPage>
  );
}
