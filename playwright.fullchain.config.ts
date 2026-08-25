/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * 全链路(浏览器 UI → agentd :8003 → 真实 LLM)验证专用 Playwright 配置。
 *
 * 用法:
 *   $env:FNIX_E2E_WORKSPACE="C:\temp\fnix_e2e_ws"
 *   npx playwright test --config=playwright.fullchain.config.ts
 *
 * 说明:
 *   - 双 webServer: vite(5175) + agentd(8003)；agentd 注入 FNIXAGENT_WORKSPACE
 *     使未指定 workspace 的请求落到隔离目录（测试与被测文件互不污染）。
 *   - workers=1 串行执行，尊重 BYOK 限流。
 */

import { defineConfig, devices } from '@playwright/test';
import { existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';

const PORT = 5175;
const API_PORT = 8003;
const WORKSPACE =
  process.env.FNIX_E2E_WORKSPACE ||
  path.join(process.cwd(), '.tmp', 'fullchain-ws');

if (!existsSync(WORKSPACE)) mkdirSync(WORKSPACE, { recursive: true });

export default defineConfig({
  testDir: './e2e/ui',
  testMatch: /fullchain-.*\.spec\.ts/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 600_000,
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: 'retain-on-failure',
    video: 'on',
  },
  webServer: [
    {
      command: 'pnpm --filter @fnixagent/workbench dev',
      url: `http://127.0.0.1:${PORT}`,
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'node scripts/run-api.mjs',
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: true,
      timeout: 120_000,
      env: {
        ...process.env,
        FNIXAGENT_WORKSPACE: WORKSPACE,
      },
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], launchOptions: { channel: 'chromium' } },
    },
  ],
});
