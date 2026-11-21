import { SourcesContent } from '../components/InfoSections.tsx';
import InfoPage from './InfoPage.tsx';

export default function SourcesPage() {
  return (
    <InfoPage
      title="Lista źródeł"
      lead="Porównujemy wiadomości tylko ze źródłami z tej listy. Lista jest jawna, żeby każdy mógł ją sprawdzić."
    >
      <SourcesContent level={2} />
    </InfoPage>
  );
}
