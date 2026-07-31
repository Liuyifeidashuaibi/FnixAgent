#!/usr/bin/env node
/**
 * Fnix Harness environment doctor — run before pnpm dev from source.
 *
 * Usage: pnpm doctor
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { detectWindowsMsvc, tauriCrateDir } from './fnix-cargo-env.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';

function ok(msg) {
  console.log(`  ✓ ${msg}`);
  return true;
}
function warn(msg) {
  console.warn(`  ⚠ ${msg}`);
  return true;
}
function fail(msg) {
  console.error(`  ✗ ${msg}`);
  return false;
}

function hasCmd(name, args = ['--version']) {
  const r = spawnSync(name, args, { encoding: 'utf-8', shell: isWin });
  return r.status === 0;
}

function checkPort(port) {
  return new Promise((resolve) => {
    import('node:net').then(({ default: net }) => {
      const s = net.createServer();
      s.once('error', () => resolve(false));
      s.once('listening', () => s.close(() => resolve(true)));
      s.listen(port, '127.0.0.1');
    });
  });
}

let passed = 0;
let failed = 0;

console.log('\nFnix Harness Doctor\n');

// Python
if (hasCmd(isWin ? 'python' : 'python3', ['--version'])) {
  ok('Python');
  passed++;
} else {
  fail('Python 3.11+ 未安装');
  failed++;
}

// Node
if (hasCmd('node', ['--version'])) {
  ok('Node.js');
  passed++;
} else {
  fail('Node.js 18+ 未安装');
  failed++;
}

// pnpm
if (hasCmd('pnpm', ['--version'])) {
  ok('pnpm');
  passed++;
} else {
  fail('pnpm 9+ 未安装（npm i -g pnpm）');
  failed++;
}

// Rust
if (hasCmd('cargo', ['--version'])) {
  ok('Rust / cargo');
  passed++;
} else {
  warn('Rust 未安装 — 无法用源码编译 Tauri；请使用 GitHub Release 安装包');
}

// Windows MSVC
if (isWin) {
  const msvc = detectWindowsMsvc();
  if (msvc.ok && msvc.path) {
    ok(`VS Build Tools: ${msvc.path}`);
    passed++;
  } else if (msvc.ok) {
    warn(msvc.reason);
  } else {
    warn(`${msvc.reason}`);
    console.warn(`    → ${msvc.hint}`);
  }
}

// .env
const envPath = path.join(root, '.env');
if (fs.existsSync(envPath)) {
  ok('.env 存在');
  passed++;
} else if (fs.existsSync(path.join(root, '.env.example'))) {
  warn('.env 不存在 — 运行 pnpm setup 或 cp .env.example .env');
} else {
  fail('.env.example 缺失');
  failed++;
}

// node_modules
if (fs.existsSync(path.join(root, 'node_modules'))) {
  ok('node_modules');
  passed++;
} else {
  warn('未 pnpm install — 运行 pnpm setup');
}

// Tauri target isolation
const tauriTarget = path.join(tauriCrateDir(), 'target');
if (process.env.CARGO_TARGET_DIR && !process.env.CARGO_TARGET_DIR.includes('FnixAgent')) {
  warn(`shell 中 CARGO_TARGET_DIR=${process.env.CARGO_TARGET_DIR} — 可能污染构建，pnpm dev 会自动覆盖`);
}
ok(`Tauri target 目录: ${tauriTarget}`);

// Ports (agentd default 8003; vite often 5175)
const portHints = {
  8003: 'agentd (default)',
  8011: 'agentd (alt)',
  5175: 'workbench vite',
  8710: 'legacy',
};
for (const port of [8003, 8011, 5175, 8710]) {
  const free = await checkPort(port);
  const label = portHints[port] || '';
  if (free) ok(`端口 ${port} 可用${label ? ` (${label})` : ''}`);
  else warn(`端口 ${port} 已被占用 — 可能已有 ${label || '服务'} 在跑`);
}

// Live agentd health (prefer occupied ports / configured base)
async function probeHealth(port) {
  try {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 1500);
    const res = await fetch(`http://127.0.0.1:${port}/health`, { signal: ctrl.signal });
    clearTimeout(t);
    return res.ok;
  } catch {
    return false;
  }
}

let apiBaseHint = process.env.VITE_API_BASE || process.env.API_TARGET || '';
const workbenchEnv = path.join(root, 'apps', 'workbench', '.env.local');
if (!apiBaseHint && fs.existsSync(workbenchEnv)) {
  const text = fs.readFileSync(workbenchEnv, 'utf8');
  const m = text.match(/^\s*VITE_API_BASE\s*=\s*(.+)$/m);
  if (m) apiBaseHint = m[1].trim().replace(/^["']|["']$/g, '');
}
const probePorts = [];
if (apiBaseHint.includes('://')) {
  try {
    const u = new URL(apiBaseHint);
    if (u.port) probePorts.push(Number(u.port));
  } catch { /* ignore */ }
}
for (const p of [8003, 8011, 8000]) {
  if (!probePorts.includes(p)) probePorts.push(p);
}
let agentdHealthy = false;
for (const port of probePorts) {
  if (await probeHealth(port)) {
    ok(`agentd /health OK on :${port}`);
    agentdHealthy = true;
    if (apiBaseHint && !apiBaseHint.includes(`:${port}`)) {
      warn(`VITE_API_BASE=${apiBaseHint} 与健康端口 :${port} 不一致 — 请改 apps/workbench/.env.local`);
    }
    break;
  }
}
if (!agentdHealthy) {
  warn('agentd 未就绪 — 开发者请先: python -m fnixagent.main serve --host 127.0.0.1 --port 8003 --no-reload');
  warn('并确保 apps/workbench/.env.local 中 VITE_API_BASE 指向同一端口');
}

// Packaged sidecar readiness (Day 15–30)
const agentdBinNames = isWin
  ? ['fnix-agentd.exe', 'agentd.exe']
  : ['fnix-agentd', 'agentd'];
const agentdDir = path.join(root, 'apps', 'workbench', 'src-tauri', 'resources', 'agentd');
const hasAgentdBin = agentdBinNames.some((n) => fs.existsSync(path.join(agentdDir, n)));
if (hasAgentdBin) {
  ok(`bundled agentd sidecar (${agentdDir})`);
  passed++;
} else {
  warn('bundled agentd 缺失 — 发行前执行: pnpm bundle:agentd');
}

try {
  const r = spawnSync(isWin ? 'python' : 'python3', ['-c', 'import PyInstaller'], {
    encoding: 'utf-8',
  });
  if (r.status === 0) ok('PyInstaller available');
  else warn('PyInstaller 未安装 — pip install pyinstaller');
} catch {
  warn('PyInstaller 检测失败');
}

console.log('\n---');
console.log('推荐路径:');
console.log('  最终用户 → GitHub Releases 安装包（无需编译）');
console.log('  开发者   → pnpm setup && pnpm doctor && pnpm dev');
console.log('  API Key  → Desktop 设置 → AI（BYOK，不必写 .env）');
console.log('  额度提示 → DashScope FreeTier 耗尽时请充值或关闭「仅免费额度」\n');

if (failed > 0) {
  console.error(`Doctor: ${failed} 项失败，${passed} 项通过`);
  process.exit(1);
}
console.log(`Doctor: 环境就绪（${passed} 项通过）`);
