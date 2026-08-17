/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Packaging shell Vite — points at apps/workbench (same UI as product).
 * Release build uses workbench `dist` via tauri.conf.json frontendDist.
 */
import path from 'node:path';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const workbenchRoot = path.resolve(__dirname, '../workbench');

export default defineConfig({
  clearScreen: false,
  root: workbenchRoot,
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.join(workbenchRoot, 'src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5175,
    strictPort: true,
  },
  build: {
    outDir: path.resolve(__dirname, 'dist'),
    emptyOutDir: true,
  },
});
