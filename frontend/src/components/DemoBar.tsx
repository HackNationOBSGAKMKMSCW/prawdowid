import { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { EXAMPLES, type Scenario } from '../api/mock.ts';
import { useChecker } from '../lib/checker.ts';
import { useGoHome } from '../lib/navigation.ts';
import MaskingDialog from './MaskingDialog.tsx';

const LINKS: { label: string; scenario: Exclude<Scenario, 'generic'> }[] = [
  { label: 'Szczepionki', scenario: 'vaccines' },
  { label: 'Most (daty)', scenario: 'analysis' },
  { label: 'Link', scenario: 'url' },
  { label: 'Opinia', scenario: 'opinion' },
  { label: 'Napisz więcej', scenario: 'clarify' },
  { label: 'Poza zakresem', scenario: 'scope' },
  { label: 'Awaria', scenario: 'failure' },
];

/** Pasek z gotowymi przykładami do pokazu. Zawsze używa danych przykładowych. */
export default function DemoBar() {
  const { run } = useChecker();
  const goHome = useGoHome();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [maskingOpen, setMaskingOpen] = useState(false);

  const runExample = (scenario: Exclude<Scenario, 'generic'>) => {
    if (pathname !== '/') navigate('/');
    run(EXAMPLES[scenario], scenario);
  };

  return (
    <>
      <div className="demo-bar" role="navigation" aria-label="Tryb demonstracyjny">
        <span className="demo-bar__label">DEMO:</span>
        <button type="button" onClick={goHome}>
          Start
        </button>
        {LINKS.map(({ label, scenario }) => (
          <button key={scenario} type="button" onClick={() => runExample(scenario)}>
            {label}
          </button>
        ))}
        {/* Okno testowe pyta prawdziwy backend (`POST /api/masking`), także w trybie mock. */}
        <button type="button" aria-haspopup="dialog" onClick={() => setMaskingOpen(true)}>
          Test maskowania
        </button>
      </div>
      {/* Poza paskiem, żeby okno nie dziedziczyło stylów `.demo-bar button`. */}
      <MaskingDialog open={maskingOpen} onClose={() => setMaskingOpen(false)} />
    </>
  );
}
