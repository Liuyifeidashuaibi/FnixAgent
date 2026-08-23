#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 本地编译 fnix-local Rust sidecar 并复制到 Desktop 资源目录
 *
 * 用法:
 *   node scripts/build-fnix-local.mjs
 *   FNIXAI_ROOT=E:\FNIX\FnixAi node scripts/build-fnix-local.mjs  # 优先姊妹仓 apps/fnix-local
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const targets = [
  path.join(root, 'apps', 'workbench', 'src-tauri', 'resources', 'fnix-local'),
];

function resolveCrateDir() {
  const sibling = process.env.FNIXAI_ROOT || process.env.FNIXAI_SIBLING;
  if (sibling) {
    const candidate = path.join(sibling, 'fnix-se', 'apps', 'fnix-local');
    if (fs.existsSync(path.join(candidate, 'Cargo.toml'))) {
      console.log('[build-fnix-local] 使用姊妹仓:', candidate);
      return candidate;
    }
  }
  const local = path.join(root, 'apps', 'fnix-local');
  if (fs.existsSync(path.join(local, 'Cargo.toml'))) {
    console.log('[build-fnix-local] 使用本仓:', local);
    return local;
  }
  console.error('[build-fnix-local] 未找到 fnix-local Cargo.toml');
  process.exit(1);
}

function binaryName() {
  return isWin ? 'fnix-local.exe' : 'fnix-local';
}

function resolveBuiltBinary(crateDir) {
  const isFnixAi = crateDir.includes(`${path.sep}fnix-se${path.sep}`);
  const metaCwd = isFnixAi ? path.join(crateDir, '..', '..') : crateDir;
  const meta = spawnSync('cargo', ['metadata', '--format-version', '1', '--no-deps'], {
    cwd: metaCwd,
    encoding: 'utf-8',
    env: {
      ...process.env,
      CARGO_TARGET_DIR: isFnixAi
        ? path.join(metaCwd, 'target')
        : process.env.CARGO_TARGET_DIR,
    },
  });
  if (meta.status !== 0) {
    console.error('[build-fnix-local] cargo metadata 失败');
    process.exit(meta.status ?? 1);
  }
  const targetDir = JSON.parse(meta.stdout).target_directory;
  return path.join(targetDir, 'release', binaryName());
}

function copyToTargets(src) {
  for (const outDir of targets) {
    fs.mkdirSync(outDir, { recursive: true });
    const dest = path.join(outDir, binaryName());
    fs.copyFileSync(src, dest);
    if (!isWin) fs.chmodSync(dest, 0o755);
    console.log('[build-fnix-local] →', dest);
  }
}

const crateDir = resolveCrateDir();
const isFnixAi = crateDir.includes(`${path.sep}fnix-se${path.sep}`);
const cargoCwd = isFnixAi ? path.join(crateDir, '..', '..') : crateDir;
const cargoArgs = isFnixAi ? ['build', '--release', '-p', 'fnix-local'] : ['build', '--release'];

console.log('[build-fnix-local] cargo', cargoArgs.join(' '), '…');
const build = spawnSync('cargo', cargoArgs, {
  cwd: cargoCwd,
  stdio: 'inherit',
  env: {
    ...process.env,
    CARGO_TARGET_DIR: isFnixAi
      ? path.join(cargoCwd, 'target')
      : process.env.CARGO_TARGET_DIR,
  },
});
if (build.status !== 0) {
  console.error('[build-fnix-local] cargo build 失败');
  process.exit(build.status ?? 1);
}

const built = resolveBuiltBinary(crateDir);
if (!fs.existsSync(built)) {
  console.error('[build-fnix-local] 未找到产物:', built);
  process.exit(1);
}

copyToTargets(built);
console.log('[build-fnix-local] 完成');
