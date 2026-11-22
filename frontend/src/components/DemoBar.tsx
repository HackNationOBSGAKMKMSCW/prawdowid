import { useLocation, useNavigate } from 'react-router-dom';
import { EXAMPLES, type Scenario } from '../api/mock.ts';
import { useChecker } from '../lib/checker.ts';
import { useGoHome } from '../lib/navigation.ts';

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

  const runExample = (scenario: Exclude<Scenario, 'generic'>) => {
    if (pathname !== '/') navigate('/');
    run(EXAMPLES[scenario], scenario);
  };

  return (
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
    </div>
  );
}
