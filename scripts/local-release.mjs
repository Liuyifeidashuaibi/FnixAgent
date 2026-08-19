#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 本地一站式发布排演 — 与 release.yml 的 job 步骤对齐(当前平台产物)。
 *
 * 用法:
 *   node scripts/local-release.mjs                 # 全链路
 *   node scripts/local-release.mjs --skip-verify   # 跳过 verify-beta(仅打包)
 *   node scripts/local-release.mjs --bundles msi   # 覆盖 bundle 类型
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { msvcDevEnv, tauriCrateDir } from './fnix-cargo-env.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const node = process.execPath;
const args = process.argv.slice(2);
const skipVerify = args.includes('--skip-verify');
const bundlesIdx = args.indexOf('--bundles');
const bundles = bundlesIdx >= 0 ? args[bundlesIdx + 1] : null;

function run(label, cmd, cmdArgs, opts = {}) {
  console.log(`\n[local-release] ▶ ${label}`);
  const r = spawnSync(cmd, cmdArgs, {
    cwd: opts.cwd || root,
    env: opts.env || msvcDevEnv(),
    stdio: 'inherit',
    shell: opts.shell ?? false,
  });
  if (r.status !== 0) {
    console.error(`[local-release] ✗ FAIL: ${label} (exit=${r.status})`);
    process.exit(r.status ?? 1);
  }
  console.log(`[local-release] ✓ ${label}`);
}

const pnpmBin = isWin ? 'pnpm.cmd' : 'pnpm';

run('step 1/7 generate app icon', isWin ? 'python' : 'python3', [
  path.join(root, 'scripts/generate-app-icon.py'),
]);

run('step 2/7 tauri icon', pnpmBin, ['exec', 'tauri', 'icon', 'app-icon.png'], {
  cwd: path.join(root, 'apps/workbench'),
  shell: isWin,
});

run('step 3/7 bundle agentd (PyInstaller)', node, [
  path.join(root, 'scripts/build-agentd-sidecar.mjs'),
]);

run('step 4/7 build fnix-local sidecar', node, [
  path.join(root, 'scripts/build-fnix-local.mjs'),
]);

if (skipVerify) {
  console.log('\n[local-release] ○ skip verify-beta (--skip-verify)');
} else {
  run('step 5/7 verify-beta', node, [path.join(root, 'scripts/verify-beta.mjs')], {
    env: { ...msvcDevEnv(), SKIP_VERIFY_BUNDLE: '1' },
  });
}

const tauriArgs = ['exec', 'tauri', 'build', '--target', 'x86_64-pc-windows-msvc'];
if (isWin) {
  tauriArgs.push(...(bundles ? ['--bundles', bundles] : ['--bundles', 'nsis']));
} else if (bundles) {
  tauriArgs.push('--bundles', bundles);
}
run('step 6/7 tauri build (full bundle)', pnpmBin, tauriArgs, {
  cwd: path.join(root, 'apps/workbench'),
  shell: isWin,
});

run('step 7/7 checksums + SBOM', node, [path.join(root, 'scripts/release-checksums.mjs')]);

console.log('\n[local-release] ═══ 本地发布排演完成 ═══');
console.log('产物目录: apps/workbench/src-tauri/target/release/bundle');
