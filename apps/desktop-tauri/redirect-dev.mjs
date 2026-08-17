#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Daily development must use apps/workbench.
 * This package is packaging-only and must not open a second "Fnix" window.
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const isWin = process.platform === 'win32';

console.error('[desktop-tauri] This package is packaging-only.');
console.error('[desktop-tauri] Redirecting to canonical shell: apps/workbench');
console.error('[desktop-tauri] Prefer: pnpm dev  (from repo root)');

const child = spawn(isWin ? 'pnpm.cmd' : 'pnpm', ['--filter', '@fnixagent/workbench', 'tauri:dev'], {
  cwd: root,
  env: process.env,
  stdio: 'inherit',
  shell: isWin,
});

child.on('exit', (code) => process.exit(code ?? 0));
