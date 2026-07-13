import { defineConfig } from 'electron-vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// electron-vite 配置 — 主进程 / preload / 渲染进程三入口
export default defineConfig({
  main: {
    build: {
      outDir: 'dist/main',
      lib: {
        entry: path.resolve(__dirname, 'src/main/index.ts'),
      },
      rollupOptions: {
        external: ['electron'],
      },
    },
  },
  preload: {
    build: {
      outDir: 'dist/preload',
      lib: {
        entry: path.resolve(__dirname, 'src/preload/index.ts'),
      },
      rollupOptions: {
        external: ['electron'],
      },
    },
  },
  renderer: {
    root: 'src/renderer',
    build: {
      outDir: 'dist/renderer',
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src/renderer'),
      },
    },
    plugins: [react()],
    server: {
      port: 5174,
    },
  },
});
