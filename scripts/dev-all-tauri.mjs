#!/usr/bin/env node
/**
 * 一键启动 Standalone：fnix-local + Python API + Tauri Desktop
 *
 * 用法：pnpm dev:all:tauri
 */
import { spawn } from 'node:child_process';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { tauriCargoEnv } from './fnix-cargo-env.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function findFreePort(start = 8000, max = 8010) {
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      if (port > max) {
        reject(new Error(`无可用端口 (${start}-${max})`));
        return;
      }
      const server = net.createServer();
      server.once('error', () => tryPort(port + 1));
      server.once('listening', () => {
        server.close(() => resolve(port));
      });
      server.listen(port, '127.0.0.1');
    };
    tryPort(start);
  });
}

function ensureEnvFile() {
  const example = path.join(root, '.env.example');
  const target = path.join(root, '.env');
  if (!fs.existsSync(target) && fs.existsSync(example)) {
    fs.copyFileSync(example, target);
    console.log('[dev:all:tauri] 已从 .env.example 创建 .env');
  }
}

function spawnProc(label, cmd, args, extraEnv = {}) {
  const child = spawn(cmd, args, {
    cwd: root,
    env: label === 'desktop-tauri' ? tauriCargoEnv(extraEnv) : { ...process.env, ...extraEnv },
    shell: isWin,
    stdio: 'inherit',
  });
  child.on('exit', (code) => {
    if (code && code !== 0) {
      console.error(`[dev:all:tauri] ${label} 退出 code=${code}`);
    }
  });
  return child;
}

async function waitForHealth(url, maxMs = 90000) {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    try {
      const res = await fetch(`${url}/health`);
      if (res.ok) {
        return await res.json();
      }
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 800));
  }
  throw new Error(`健康检查超时: ${url}/health`);
}

ensureEnvFile();

const profile = process.env.FNIXAGENT_PROFILE || 'standalone';
let apiPort;
let localPort;
try {
  apiPort = await findFreePort(8000, 8020);
  localPort = await findFreePort(8710, 8720);
} catch (e) {
  console.error('[dev:all:tauri]', e instanceof Error ? e.message : e);
  process.exit(1);
}

const apiBase = `http://127.0.0.1:${apiPort}`;
const localBase = `http://127.0.0.1:${localPort}`;
const baseEnv = {
  PYTHONPATH: path.join(root, 'src'),
  FNIXAGENT_PROFILE: profile,
  SERVICE_ENV: 'development',
  SERVICE_DEBUG: 'true',
  fnixagent_BACKEND_URL: apiBase,
  VITE_API_BASE: apiBase,
  FNIX_LOCAL_URL: localBase,
  FNIX_LOCAL_MANAGED: 'false',
};

console.log('[dev:all:tauri] FnixAgent Standalone + Tauri 2 Desktop');
console.log(`[dev:all:tauri] profile=${profile}  API=${apiBase}  fnix-local=${localBase}`);

const local = spawnProc(
  'fnix-local',
  python,
  ['-m', 'fnixagent.local'],
  {
    ...baseEnv,
    FNIX_LOCAL_HOST: '127.0.0.1',
    FNIX_LOCAL_PORT: String(localPort),
  },
);

try {
  const localHealth = await waitForHealth(localBase, 45000);
  console.log('[dev:all:tauri] fnix-local 就绪:', localHealth);
} catch (e) {
  console.warn('[dev:all:tauri] fnix-local 未就绪（将降级）:', e instanceof Error ? e.message : e);
}

const api = spawnProc(
  'api',
  python,
  ['-m', 'fnixagent.main', 'serve', '--no-reload', '--host', '127.0.0.1', '--port', String(apiPort)],
  baseEnv,
);

try {
  const health = await waitForHealth(apiBase);
  console.log('[dev:all:tauri] 后端就绪:', health);
} catch (e) {
  console.warn('[dev:all:tauri]', e instanceof Error ? e.message : e);
  console.warn('[dev:all:tauri] 仍尝试启动 Tauri Desktop…');
}

const desktop = spawnProc(
  'workbench',
  isWin ? 'pnpm.cmd' : 'pnpm',
  ['--filter', '@fnixagent/workbench', 'tauri:dev'],
  baseEnv,
);

function shutdown() {
  api.kill('SIGTERM');
  local.kill('SIGTERM');
  desktop.kill('SIGTERM');
  process.exit(0);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
