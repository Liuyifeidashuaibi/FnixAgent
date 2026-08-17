#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Clean-VM / no-system-Python smoke for packaged sidecars.
 *
 * Verifies:
 *  1. Bundled fnix-agentd binary exists and /health works
 *  2. Bundled fnix-local (if present) /health works
 *  3. Capability token gate rejects anonymous mutating calls
 *
 * Usage: node scripts/smoke-clean-vm.mjs
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const agentdDir = path.join(root, 'apps', 'workbench', 'src-tauri', 'resources', 'agentd');
const sidecarDir = path.join(root, 'apps', 'workbench', 'src-tauri', 'resources', 'fnix-local');
const token = `smoke-${Date.now().toString(36)}`;

function findBinary(dir, names) {
  for (const name of names) {
    const p = path.join(dir, name);
    if (fs.existsSync(p) && fs.statSync(p).isFile()) return p;
  }
  return null;
}

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close(() => resolve(port));
    });
    s.on('error', reject);
  });
}

async function waitHealth(url, ms = 45000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    try {
      const res = await fetch(`${url}/health`, { signal: AbortSignal.timeout(1500) });
      if (res.ok) return true;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

function startProc(bin, args, env) {
  return spawn(bin, args, {
    cwd: path.dirname(bin),
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
}

async function kill(child) {
  if (!child || child.killed) return;
  child.kill('SIGTERM');
  await new Promise((r) => setTimeout(r, 500));
  try {
    child.kill('SIGKILL');
  } catch {
    /* ignore */
  }
}

const agentdBin = findBinary(agentdDir, isWin ? ['fnix-agentd.exe', 'agentd.exe'] : ['fnix-agentd', 'agentd']);
if (!agentdBin) {
  console.error('[smoke-clean-vm] FAIL: bundled fnix-agentd missing — run: pnpm bundle:agentd');
  process.exit(1);
}

const children = [];
let failed = 0;

try {
  const agentPort = await freePort();
  const apiBase = `http://127.0.0.1:${agentPort}`;
  console.log('[smoke-clean-vm] starting bundled agentd on', apiBase);
  const agentd = startProc(
    agentdBin,
    ['serve', '--no-reload', '--host', '127.0.0.1', '--port', String(agentPort)],
    {
      FNIXAGENT_PROFILE: 'standalone',
      SERVICE_DEBUG: 'true',
      FNIX_CAPABILITY_TOKEN: token,
      FNIXAGENT_BACKEND_URL: apiBase,
    },
  );
  children.push(agentd);

  if (!(await waitHealth(apiBase))) {
    console.error('[smoke-clean-vm] FAIL: agentd /health timeout');
    failed++;
  } else {
    console.log('[smoke-clean-vm] OK agentd /health');
  }

  // Public health must work without capability header.
  const health = await fetch(`${apiBase}/health`);
  if (!health.ok) {
    console.error('[smoke-clean-vm] FAIL: public /health');
    failed++;
  }

  // Mutating harness route must require capability when token is set.
  const denied = await fetch(`${apiBase}/api/v1/harness/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider: 'smoke' }),
  });
  if (denied.status !== 401) {
    console.error('[smoke-clean-vm] FAIL: expected 401 without capability, got', denied.status);
    failed++;
  } else {
    console.log('[smoke-clean-vm] OK capability gate (401 without token)');
  }

  const allowed = await fetch(`${apiBase}/api/v1/harness/config`, {
    headers: { 'X-Fnix-Capability': token },
  });
  if (!allowed.ok) {
    console.error('[smoke-clean-vm] FAIL: harness/config with token →', allowed.status);
    failed++;
  } else {
    console.log('[smoke-clean-vm] OK harness/config with capability');
  }

  const sidecarBin = findBinary(
    sidecarDir,
    isWin
      ? ['fnix-local.exe', 'fnix-local-windows-x64.exe']
      : ['fnix-local', 'fnix-local-linux-x64', 'fnix-local-macos-universal'],
  );
  if (sidecarBin) {
    const sidePort = await freePort();
    const sideBase = `http://127.0.0.1:${sidePort}`;
    console.log('[smoke-clean-vm] starting bundled fnix-local on', sideBase);
    const side = startProc(sidecarBin, ['--host', '127.0.0.1', '--port', String(sidePort)], {
      FNIX_LOCAL_HOST: '127.0.0.1',
      FNIX_LOCAL_PORT: String(sidePort),
      FNIX_CAPABILITY_TOKEN: token,
    });
    children.push(side);
    if (!(await waitHealth(sideBase, 20000))) {
      console.error('[smoke-clean-vm] FAIL: fnix-local /health timeout');
      failed++;
    } else {
      console.log('[smoke-clean-vm] OK fnix-local /health');
    }
  } else {
    console.warn('[smoke-clean-vm] skip fnix-local (binary not in resources)');
  }
} finally {
  for (const child of children) await kill(child);
}

if (failed) {
  console.error(`[smoke-clean-vm] FAIL (${failed} checks)`);
  process.exit(1);
}
console.log('[smoke-clean-vm] PASS — bundled sidecars ready without system Python');
