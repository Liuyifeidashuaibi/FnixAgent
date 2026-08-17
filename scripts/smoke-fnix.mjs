#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Fnix product smoke: home + setup/doctor + harness API.
 * Validates FNIX_PRODUCT.md P0 path.
 * Usage: pnpm smoke:fnix
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function run(label, cmd, args, env = {}) {
  const r = spawnSync(cmd, args, {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: path.join(root, 'src'),
      FNIXAGENT_PROFILE: 'standalone',
      ...env,
    },
    shell: isWin,
    encoding: 'utf-8',
  });
  if (r.status !== 0) {
    console.error(`[fnix-smoke] FAIL ${label}`);
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    process.exit(r.status ?? 1);
  }
  console.log(`[fnix-smoke] OK ${label}`);
  return r;
}

function findFreePort(start = 8020) {
  return new Promise((resolve) => {
    const tryPort = (port) => {
      const s = net.createServer();
      s.once('error', () => tryPort(port + 1));
      s.once('listening', () => s.close(() => resolve(port)));
      s.listen(port, '127.0.0.1');
    };
    tryPort(start);
  });
}

const smokeHome = path.join(root, '.fnix-smoke-test');
fs.rmSync(smokeHome, { recursive: true, force: true });

run(
  'pytest home',
  python,
  ['-m', 'pytest', 'tests/unit/test_harness_home.py', 'tests/unit/test_harness_secrets.py', '-q'],
  {
    FNIX_HOME: smokeHome,
  },
);
run('pytest harness config', python, ['-m', 'pytest', 'tests/unit/test_harness_config.py', '-q'], {
  FNIX_HOME: smokeHome,
});
run('cli doctor', python, ['-m', 'fnixagent', 'doctor'], { FNIX_HOME: smokeHome });
run(
  'cli setup non-interactive',
  python,
  [
    '-m',
    'fnixagent',
    'setup',
    '--non-interactive',
    '--provider',
    'qwen',
    '--model',
    'qwen-plus',
    '--api-key',
    'sk-smoke-test',
  ],
  { FNIX_HOME: smokeHome },
);
run('cli model', python, ['-m', 'fnixagent', 'model'], { FNIX_HOME: smokeHome });

const port = await findFreePort(8020);
const apiBase = `http://127.0.0.1:${port}`;

const proc = spawn(
  python,
  [
    '-m',
    'uvicorn',
    'fnixagent.main:app',
    '--host',
    '127.0.0.1',
    '--port',
    String(port),
    '--log-level',
    'warning',
  ],
  {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: path.join(root, 'src'),
      FNIXAGENT_PROFILE: 'standalone',
      SERVICE_DEBUG: 'true',
      FNIX_API_ONLY: '1',
      FNIX_HOME: smokeHome,
    },
    stdio: 'ignore',
    shell: isWin,
  },
);

async function waitHealth(maxMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(`${apiBase}/health`);
      if (res.ok) return await res.json();
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error('API health timeout');
}

try {
  const health = await waitHealth();
  console.log('[fnix-smoke] OK health', health.profile || 'standalone');

  const status = await fetch(`${apiBase}/api/v1/harness/status`);
  if (!status.ok) throw new Error(`harness/status ${status.status}`);
  const st = await status.json();
  if (!st.ready) throw new Error('harness not ready after setup');
  console.log('[fnix-smoke] OK harness/status ready');

  console.log('\n[fnix-smoke] 全部通过 — setup/doctor/home/API 就绪\n');
} finally {
  proc.kill();
  fs.rmSync(smokeHome, { recursive: true, force: true });
}
