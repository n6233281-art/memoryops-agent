import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The dashboard talks to the FastAPI backend through this dev proxy, so the
// frontend never needs to know the backend host.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
});
