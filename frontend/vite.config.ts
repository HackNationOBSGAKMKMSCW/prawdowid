import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// Nazwy hostów Tailscale (MagicDNS, `tailscale serve`), np. moj-mac.tail1234.ts.net.
// Bez tego Vite odrzuca żądania z obcą nazwą hosta (ochrona przed DNS rebinding).
const allowedHosts = ['.ts.net'];

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // Dwa osobne backendy w dev:
  //   /api/whatsapp → symulator WhatsApp (whatsapp_sim, `python -m whatsappAdapter --port 8001`)
  //   /api          → API strony (`uvicorn server:app --port 8000`): /check, /health, /trusted-sources
  // Kolejność ma znaczenie: bardziej szczegółowa ścieżka musi być pierwsza.
  const proxy = {
    '/api/whatsapp': env.WHATSAPP_PROXY_TARGET || 'http://127.0.0.1:8001',
    '/api': env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
  };
  return {
    plugins: [react()],
    server: { allowedHosts, proxy },
    preview: { allowedHosts, proxy },
  };
});
