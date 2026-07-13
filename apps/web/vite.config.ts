import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// OfficeAgent Web 应用 Vite 配置
// 开发服务器默认 5173 端口,代理 /api 到后端 8000
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
