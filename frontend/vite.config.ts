import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Nazwy hostów Tailscale (MagicDNS, `tailscale serve`), np. moj-mac.tail1234.ts.net.
// Bez tego Vite odrzuca żądania z obcą nazwą hosta (ochrona przed DNS rebinding).
const allowedHosts = ['.ts.net'];

// Wspólny plik `.env` projektu leży w katalogu głównym repo.
const envDir = '..';

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, '');
  // `npm run dev:live` / `build:live` (`--mode live`): strona łączy się z prawdziwym API.
  // Tryb zamiast `VITE_API_MODE=live vite`, bo takiej składni nie obsługuje npm na Windowsie.
  if (mode === 'live') process.env.VITE_API_MODE ??= 'live';
  // Jeden backend w dev: API strony (`uvicorn server:app --port 8000`) obsługuje też
  // symulator WhatsApp (/api/whatsapp/*, ta sama weryfikacja co /api/check).
  // WHATSAPP_PROXY_TARGET kieruje /api/whatsapp gdzie indziej, np. na osobny adapter
  // demo (`python -m whatsappAdapter --demo --port 8001`).
  const apiTarget = env.API_PROXY_TARGET || 'http://127.0.0.1:8000';
  const proxy = {
    '/api/whatsapp': env.WHATSAPP_PROXY_TARGET || apiTarget,
    '/api': apiTarget,
  };
  return {
    envDir,
    plugins: [react()],
    server: { allowedHosts, proxy },
    preview: { allowedHosts, proxy },
  };
});
