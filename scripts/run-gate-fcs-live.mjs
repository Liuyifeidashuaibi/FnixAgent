#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Live curated FCS + Work golden gate.
 *
 * Requires:
 *   - agentd healthy (default http://127.0.0.1:8003)
 *   - DASHSCOPE_API_KEY or OPENAI_API_KEY in .env / env
 *
 * Usage:
 *   pnpm gate:fcs:live
 *   GATE_WORK_GOLDEN_LIMIT=2 pnpm gate:fcs:live   # smoke fewer Work scenes
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const env = {
  ...process.env,
  GATE_FCS_LIVE: '1',
  FNIX_API_BASE:
    process.env.FNIX_API_BASE ||
    process.env.VITE_API_BASE ||
    process.env.FNIXAGENT_BACKEND_URL ||
    'http://127.0.0.1:8003',
  VITE_API_BASE:
    process.env.VITE_API_BASE ||
    process.env.FNIX_API_BASE ||
    process.env.FNIXAGENT_BACKEND_URL ||
    'http://127.0.0.1:8003',
};

const r = spawnSync(process.execPath, [path.join(root, 'scripts/gate-curated-fcs.mjs')], {
  cwd: root,
  env,
  stdio: 'inherit',
});

process.exit(r.status ?? 1);
