import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['src/__tests__/**/*.test.ts'],
    exclude: [
      'node_modules',
      'dist',
      '.fnix-backups',
      '.fnix-snapshots',
      // Legacy tests use process.exit() and custom harnesses — run via npx tsx
      'src/__tests__/security-scanner.integration.test.ts',
      'src/__tests__/multi-agent.integration.test.ts',
    ],
    environment: 'node',
    globals: false,
  },
})
