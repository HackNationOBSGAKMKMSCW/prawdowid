import { lazy, Suspense } from 'react';
import { Route, Routes } from 'react-router-dom';
import { API_MODE } from './api/client.ts';
import DemoBar from './components/DemoBar.tsx';
import Footer from './components/Footer.tsx';
import Header from './components/Header.tsx';
import ViewSwitch from './components/ViewSwitch.tsx';
import { AnnouncerProvider } from './lib/announcer.tsx';
import { CheckerContext, useChecker, useCheckerState } from './lib/checker.ts';
import { SpeechProvider } from './lib/SpeechProvider.tsx';
import { usePreferences } from './lib/usePreferences.ts';
import AccessibilityPage from './pages/AccessibilityPage.tsx';
import HelpPage from './pages/HelpPage.tsx';
import NotFound from './pages/NotFound.tsx';
import SourcesPage from './pages/SourcesPage.tsx';
import CheckPage from './screens/CheckPage.tsx';

const SHOW_DEMO_BAR =
  import.meta.env.VITE_DEMO_BAR === 'true' ||
  (import.meta.env.VITE_DEMO_BAR !== 'false' && API_MODE === 'mock');

// Czat ładuje się dopiero po wejściu w widok WhatsApp.
const WhatsAppView = lazy(() => import('./whatsapp/WhatsAppView.tsx'));

export default function App() {
  // Stan sprawdzania i ustawienia wyglądu żyją nad trasami, więc przejście do
  // WhatsAppa i z powrotem nie gubi wyniku.
  const prefs = usePreferences();
  const checker = useCheckerState();

  return (
    <CheckerContext.Provider value={checker}>
      <Routes>
        <Route
          path="/whatsapp"
          element={
            <Suspense fallback={null}>
              <WhatsAppView />
            </Suspense>
          }
        />
        <Route path="*" element={<WebApp prefs={prefs} />} />
      </Routes>
    </CheckerContext.Provider>
  );
}

/** Pierwszy widok: strona do sprawdzania wiadomości. */
function WebApp({ prefs }: { prefs: ReturnType<typeof usePreferences> }) {
  const checking = useChecker().screen.name === 'checking';

  return (
    <AnnouncerProvider>
      <SpeechProvider autoRead={prefs.readAloud} onToggleAutoRead={prefs.toggleReadAloud}>
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
              dark={prefs.theme === 'dark'}
              onToggleTheme={prefs.toggleTheme}
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
          {/* Na końcu kolejności Tab, zgodnie z położeniem w prawym dolnym rogu. */}
          <ViewSwitch />
        </div>
      </SpeechProvider>
    </AnnouncerProvider>
  );
}
