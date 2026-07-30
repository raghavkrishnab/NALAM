import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Override when the backend is not on the default port, e.g.
//   VITE_API_TARGET=http://127.0.0.1:8001 npm run dev
const API_TARGET = process.env.VITE_API_TARGET || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy keeps the browser on one origin, so no CORS surprises during a demo.
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});
