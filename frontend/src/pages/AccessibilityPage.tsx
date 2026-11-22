import { AccessibilityContent } from '../components/InfoSections.tsx';
import InfoPage from './InfoPage.tsx';

export default function AccessibilityPage() {
  return (
    <InfoPage
      title="Deklaracja dostępności"
      lead="Chcemy, żeby z Prawdowida mógł korzystać każdy, także osoby z niepełnosprawnościami i osoby starsze."
    >
      <AccessibilityContent level={2} />
    </InfoPage>
  );
}
