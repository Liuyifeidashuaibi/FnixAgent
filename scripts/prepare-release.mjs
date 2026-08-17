#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 发布前准备 — 图标 + Python bundle + Beta 验收
 *
 * 用法: pnpm prepare:release
 * 完整安装包: pnpm --filter @fnixagent/workbench tauri:build
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tauriRoot = path.join(root, 'apps', 'workbench');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function run(label, cmd, args, cwd = root, shell = false) {
  console.log(`\n[release] ▶ ${label}`);
  const r = spawnSync(cmd, args, { cwd, shell, stdio: 'inherit' });
  if (r.status !== 0) {
    console.error(`[release] ✗ ${label}`);
    process.exit(r.status ?? 1);
  }
}

const node = process.execPath;

run('generate app-icon', python, [path.join(root, 'scripts/generate-app-icon.py')], root, isWin);
run('build agentd sidecar', node, [path.join(root, 'scripts/build-agentd-sidecar.mjs')], root, isWin);
run('fetch fnix-local', node, [path.join(root, 'scripts/fetch-fnix-local.mjs')], root, isWin);
run('smoke clean-vm sidecars', node, [path.join(root, 'scripts/smoke-clean-vm.mjs')], root, isWin);
run('tauri icon', isWin ? 'pnpm.cmd' : 'pnpm', ['exec', 'tauri', 'icon', 'app-icon.png'], tauriRoot, isWin);
run('verify:beta', isWin ? 'pnpm.cmd' : 'pnpm', ['verify:beta'], root, isWin);
run('release checksums', node, [path.join(root, 'scripts/release-checksums.mjs')], root, isWin);

console.log('\n[release] 准备完成。打包: pnpm --filter @fnixagent/workbench tauri:build');
