import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// Admin 后台独立 Vite 应用(端口 5175)
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
