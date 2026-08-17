#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 完整 Harness E2E — standalone 后端 + harness/session/apply 全路径
 * 用法: pnpm e2e:full
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
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`health timeout: ${url}`);
}

function spawnProc(cmd, args, env) {
  return spawn(cmd, args, {
    cwd: root,
    env: { ...process.env, ...env },
    stdio: 'ignore',
    shell: isWin,
  });
}

async function main() {
  const localPort = await findFreePort(8710, 8799);
  const apiPort = await findFreePort(8000, 8099);
  const apiBase = `http://127.0.0.1:${apiPort}`;
  const tmpWs = fs.mkdtempSync(path.join(root, '.tmp-e2e-ws-'));

  const env = {
    FNIXAGENT_PROFILE: 'standalone',
    PYTHONPATH: path.join(root, 'src'),
    FNIX_LOCAL_URL: `http://127.0.0.1:${localPort}`,
    FNIX_LOCAL_PORT: String(localPort),
    FNIX_API_PORT: String(apiPort),
    FNIX_LOCAL_MANAGED: 'false',
  };

  const localProc = spawnProc(python, ['-m', 'fnixagent.local'], env);
  const apiProc = spawnProc(python, ['-m', 'fnixagent.main', 'serve', '--port', String(apiPort)], env);

  const killAll = () => {
    try {
      localProc.kill();
    } catch {
      /* ignore */
    }
    try {
      apiProc.kill();
    } catch {
      /* ignore */
    }
  };

  process.on('exit', killAll);
  process.on('SIGINT', () => {
    killAll();
    process.exit(130);
  });

  try {
    await waitHealth(`http://127.0.0.1:${localPort}`);
    await waitHealth(apiBase);

    // register + login
    await fetch(`${apiBase}/api/v1/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: 'e2e_full',
        email: 'e2e@fnix.local',
        password: 'secret123',
        role: 'user',
      }),
    });
    const loginRes = await fetch(`${apiBase}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'e2e_full', password: 'secret123' }),
    });
    if (!loginRes.ok) throw new Error(`login ${loginRes.status}`);
    const { access_token: token } = await loginRes.json();
    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };

    // harness ensure + index
    const ensureRes = await fetch(`${apiBase}/api/v1/harness/workspace/ensure`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ workspace: tmpWs }),
    });
    if (!ensureRes.ok) throw new Error(`ensure ${ensureRes.status}`);

    const indexRes = await fetch(`${apiBase}/api/v1/harness/index`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ workspace: tmpWs }),
    });
    if (!indexRes.ok) throw new Error(`index ${indexRes.status}`);

    // code apply
    const applyRes = await fetch(`${apiBase}/api/v1/chat/agent/apply`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        workspace: tmpWs,
        changes: [{ path: 'e2e.txt', action: 'create', content: 'full e2e\n' }],
      }),
    });
    if (!applyRes.ok) throw new Error(`apply ${applyRes.status}`);
    const applyBody = await applyRes.json();
    if (!applyBody.ok) throw new Error(applyBody.error || 'apply failed');

    const filePath = path.join(tmpWs, 'e2e.txt');
    if (!fs.existsSync(filePath)) throw new Error('file not written');
    const written = fs.readFileSync(filePath, 'utf-8');
    if (!written.includes('full e2e')) throw new Error(`file content mismatch: ${JSON.stringify(written)}`);

    // sessions list
    const sessRes = await fetch(`${apiBase}/api/v1/work/sessions?workspace=${encodeURIComponent(tmpWs)}`, {
      headers,
    });
    if (!sessRes.ok) throw new Error(`sessions ${sessRes.status}`);

    console.log('[e2e:full] OK — harness + apply + sessions');
  } finally {
    killAll();
    try {
      fs.rmSync(tmpWs, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  }
}

main().catch((e) => {
  console.error('[e2e:full] FAIL', e.message || e);
  process.exit(1);
});
