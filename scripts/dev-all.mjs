#!/usr/bin/env node
/**
 * 一键启动 Standalone — 转发到 Tauri 三进程（主路径）
 *
 * @deprecated 直接 `pnpm dev:all:tauri` 等价；Electron 见 dev:electron
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const script = path.join(root, 'scripts', 'dev-all-tauri.mjs');

console.log('[dev:all] → Tauri 2 Desktop（主产品）');

const child = spawn(process.execPath, [script], {
  cwd: root,
  env: process.env,
  stdio: 'inherit',
});

child.on('exit', (code) => process.exit(code ?? 0));

process.on('SIGINT', () => child.kill('SIGINT'));
process.on('SIGTERM', () => child.kill('SIGTERM'));
