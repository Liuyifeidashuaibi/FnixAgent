#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Start the canonical desktop shell: apps/workbench (Tauri).
 * Windows loads MSVC via vcvars PATH merge.
 *
 * Historical note: this script used to launch apps/desktop-tauri, which shares
 * the same productName/identifier and fights workbench for :5175 / WebView data.
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { detectWindowsMsvc, msvcDevEnv } from './fnix-cargo-env.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tauriApp = path.join(root, 'apps', 'workbench');
const isWin = process.platform === 'win32';

if (isWin) {
  const msvc = detectWindowsMsvc();
  if (!msvc.ok) {
    console.error('[tauri-dev]', msvc.reason);
    console.error(' ', msvc.hint);
    process.exit(1);
  }
}

console.log('[tauri-dev] canonical shell = apps/workbench (not desktop-tauri)');

const child = spawn(isWin ? 'pnpm.cmd' : 'pnpm', ['exec', 'tauri', 'dev'], {
  cwd: tauriApp,
  env: msvcDevEnv(),
  stdio: 'inherit',
  shell: isWin,
});

child.on('exit', (code) => process.exit(code ?? 0));
