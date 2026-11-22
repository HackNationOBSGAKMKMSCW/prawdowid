import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// Nazwy hostów Tailscale (MagicDNS, `tailscale serve`), np. moj-mac.tail1234.ts.net.
// Bez tego Vite odrzuca żądania z obcą nazwą hosta (ochrona przed DNS rebinding).
const allowedHosts = ['.ts.net'];

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  preview: {
    allowedHosts,
  },
});
