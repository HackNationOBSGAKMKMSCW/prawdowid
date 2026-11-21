import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';

// The admin API address is not hard-coded in the app: the browser calls
// `apiBaseUrl` from public/config.json (or VITE_ADMIN_API_URL). In development
// a relative base such as `/api/admin` is proxied to ADMIN_API_PROXY_TARGET.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      port: 5175,
      proxy: {
        '/api': env.ADMIN_API_PROXY_TARGET || 'http://127.0.0.1:8000',
      },
    },
  };
});
