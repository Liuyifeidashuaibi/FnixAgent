/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

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
