import { Route, Routes } from 'react-router-dom';
import { API_MODE } from './api/client.ts';
import DemoBar from './components/DemoBar.tsx';
import Footer from './components/Footer.tsx';
import Header from './components/Header.tsx';
import { AnnouncerProvider } from './lib/announcer.tsx';
import { CheckerContext, useCheckerState } from './lib/checker.ts';
import { usePreferences } from './lib/usePreferences.ts';
import AccessibilityPage from './pages/AccessibilityPage.tsx';
import HelpPage from './pages/HelpPage.tsx';
import NotFound from './pages/NotFound.tsx';
import SourcesPage from './pages/SourcesPage.tsx';
import CheckPage from './screens/CheckPage.tsx';

const SHOW_DEMO_BAR =
  import.meta.env.VITE_DEMO_BAR === 'true' ||
  (import.meta.env.VITE_DEMO_BAR !== 'false' && API_MODE === 'mock');

export default function App() {
  const prefs = usePreferences();
  const checker = useCheckerState();
  const checking = checker.screen.name === 'checking';

  return (
    <CheckerContext.Provider value={checker}>
      <AnnouncerProvider>
        <div className="app" lang="pl" data-hc={prefs.highContrast}>
          <a href="#tresc" className="skip-link">
            Przejdź do treści
          </a>
          {SHOW_DEMO_BAR && <DemoBar />}
          <div className="shell" data-big={prefs.bigText} aria-busy={checking}>
            <Header
              bigText={prefs.bigText}
              highContrast={prefs.highContrast}
              onToggleBigText={prefs.toggleBigText}
              onToggleHighContrast={prefs.toggleHighContrast}
            />
            <main id="tresc" className="main" tabIndex={-1}>
              <Routes>
                <Route path="/" element={<CheckPage />} />
                <Route path="/zrodla" element={<SourcesPage />} />
                <Route path="/pomoc" element={<HelpPage />} />
                <Route path="/deklaracja-dostepnosci" element={<AccessibilityPage />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
            <Footer />
          </div>
        </div>
      </AnnouncerProvider>
    </CheckerContext.Provider>
  );
}
