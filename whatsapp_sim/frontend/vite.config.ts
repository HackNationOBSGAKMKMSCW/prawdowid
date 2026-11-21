import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The WhatsApp adapter (whatsapp_sim/backend) listens on port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
