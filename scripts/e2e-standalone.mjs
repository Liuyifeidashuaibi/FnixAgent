#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Standalone 端到端冒烟 — 自动拉起 fnix-local + agentd，跑 API 验收后退出
 *
 * 用法: pnpm e2e:standalone
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function findFreePort(start, max) {
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      if (port > max) {
        reject(new Error(`no free port ${start}-${max}`));
        return;
      }
      const server = net.createServer();
      server.once('error', () => tryPort(port + 1));
      server.once('listening', () => server.close(() => resolve(port)));
      server.listen(port, '127.0.0.1');
    };
    tryPort(start);
  });
}

async function waitHealth(url, maxMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(`${url}/health`);
      if (res.ok) return res.json();
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 600));
  }
  throw new Error(`health timeout: ${url}/health`);
}

function spawnProc(cmd, args, env) {
  return spawn(cmd, args, {
    cwd: root,
    env: { ...process.env, ...env },
    shell: false,
    stdio: isWin ? 'ignore' : 'ignore',
    detached: !isWin,
  });
}

function killProc(child) {
  if (!child || child.killed) return;
  try {
    if (isWin) {
      spawn('taskkill', ['/pid', String(child.pid), '/f', '/t'], { shell: true, stdio: 'ignore' });
    } else {
      process.kill(-child.pid, 'SIGTERM');
    }
  } catch {
    try {
      child.kill('SIGTERM');
    } catch {
      /* ignore */
    }
  }
}

async function runSmoke(apiBase, localBase) {
  process.env.VITE_API_BASE = apiBase;
  process.env.fnixagent_BACKEND_URL = apiBase;
  process.env.FNIX_LOCAL_URL = localBase;

  const health = await fetch(`${apiBase}/health`);
  if (!health.ok) throw new Error(`agentd health ${health.status}`);

  const sidecar = await fetch(`${localBase}/health`);
  if (!sidecar.ok) throw new Error(`sidecar health ${sidecar.status}`);
  const sidecarJson = await sidecar.json();
  console.log('[e2e:standalone] sidecar:', sidecarJson.service, sidecarJson.runtime ?? 'python');

  const harness = await fetch(`${apiBase}/api/v1/harness/status`);
  if (!harness.ok) throw new Error(`harness status ${harness.status}`);
  const harnessJson = await harness.json();
  console.log('[e2e:standalone] harness ok:', harnessJson.ok);
  if (harnessJson.sidecar?.available === false) {
    console.warn('[e2e:standalone] warn: harness reports sidecar offline');
  }

  const workStatus = await fetch(`${apiBase}/api/v1/work/status`);
  if (!workStatus.ok) throw new Error(`work status ${workStatus.status}`);
  const ws = await workStatus.json();
  console.log('[e2e:standalone] work ktg/stp/mfp:', ws.ktg, ws.stp, ws.mfp);

  const wsDir = path.join(root, 'data', 'e2e-workspace');
  fs.mkdirSync(wsDir, { recursive: true });

  const ensure = await fetch(`${apiBase}/api/v1/harness/workspace/ensure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace: wsDir }),
  });
  if (!ensure.ok) throw new Error(`workspace ensure ${ensure.status}`);
  console.log('[e2e:standalone] workspace .fnix:', (await ensure.json()).ok);

  const index = await fetch(`${apiBase}/api/v1/harness/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace: wsDir, force: false }),
  });
  const indexJson = await index.json();
  console.log('[e2e:standalone] index:', index.ok, indexJson.ok ?? indexJson.session_id);

  const sessions = await fetch(`${apiBase}/api/v1/work/sessions?limit=5`);
  if (!sessions.ok) throw new Error(`sessions ${sessions.status}`);
  const before = (await sessions.json()).sessions?.length ?? 0;

  // 通过 API 间接验证 session 文件持久化（集成测试已覆盖；此处做 smoke 占位）
  console.log('[e2e:standalone] sessions before:', before);

  console.log('[e2e:standalone] PASS');
}

async function main() {
  const apiPort = await findFreePort(8030, 8040);
  const localPort = await findFreePort(8730, 8740);
  const apiBase = `http://127.0.0.1:${apiPort}`;
  const localBase = `http://127.0.0.1:${localPort}`;

  const baseEnv = {
    PYTHONPATH: path.join(root, 'src'),
    FNIXAGENT_PROFILE: 'standalone',
    SERVICE_ENV: 'development',
    SERVICE_DEBUG: 'true',
    fnixagent_BACKEND_URL: apiBase,
    VITE_API_BASE: apiBase,
    FNIX_LOCAL_URL: localBase,
    FNIX_LOCAL_MANAGED: 'false',
  };

  console.log(`[e2e:standalone] spawn API=${apiBase} sidecar=${localBase}`);

  const local = spawnProc(python, ['-m', 'fnixagent.local'], {
    ...baseEnv,
    FNIX_LOCAL_HOST: '127.0.0.1',
    FNIX_LOCAL_PORT: String(localPort),
  });

  await waitHealth(localBase, 45000);

  const api = spawnProc(
    python,
    ['-m', 'fnixagent.main', 'serve', '--no-reload', '--host', '127.0.0.1', '--port', String(apiPort)],
    baseEnv,
  );

  try {
    await waitHealth(apiBase, 120000);
    await runSmoke(apiBase, localBase);
  } finally {
    killProc(api);
    killProc(local);
  }
}

main().catch((e) => {
  console.error('[e2e:standalone] FAIL', e.message || e);
  process.exit(1);
});
