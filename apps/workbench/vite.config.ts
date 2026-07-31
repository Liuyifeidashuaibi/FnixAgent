import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// 端口单一来源：所有 API 请求走 vite proxy → 127.0.0.1:8003
// 优先读 FNIX_AGENTD_URL（统一环境变量名），fallback VITE_API_BASE，再 fallback 默认地址。
// .env 一处配置 FNIX_AGENTD_URL=http://127.0.0.1:8003 即可。
// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = (env.FNIX_AGENTD_URL || env.VITE_API_BASE || env.API_TARGET || 'http://127.0.0.1:8003').replace(/\/$/, '')

  return {
  server: {
    host: '127.0.0.1',
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
      '/health': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  base: './',
  plugins: [react(), tailwindcss()],

  optimizeDeps: {
    // web-tree-sitter uses WebAssembly.instantiateStreaming internally.
    // Vite's dep optimizer wraps modules in a way that breaks WASM loading.
    exclude: ['web-tree-sitter'],
  },

  worker: {
    // Debt analyzer worker uses ES module syntax and ?url imports.
    format: 'es',
  },

  build: {
    rollupOptions: {
      output: {
        // Keep WASM files in a stable location — ?url imports in ASTEngine.ts
        // resolve to these paths at build time. Hashing is fine; the ?url
        // import captures the hashed name automatically.
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith('.wasm')) {
            return 'assets/wasm/[name][extname]'   // no hash — stable URL for worker context
          }
          return 'assets/[name]-[hash][extname]'
        },
      },
    },
  },
  }
})

