#!/usr/bin/env node
/**
 * One-shot setup for open-source developers.
 * Usage: pnpm setup
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function run(label, cmd, args, opts = {}) {
  console.log(`\n[setup] ▶ ${label}`);
  const r = spawnSync(cmd, args, {
    cwd: opts.cwd || root,
    stdio: 'inherit',
    shell: isWin,
    env: process.env,
  });
  if (r.status !== 0) {
    console.error(`[setup] ✗ ${label}`);
    process.exit(r.status ?? 1);
  }
}

if (!fs.existsSync(path.join(root, '.env')) && fs.existsSync(path.join(root, '.env.example'))) {
  fs.copyFileSync(path.join(root, '.env.example'), path.join(root, '.env'));
  console.log('[setup] 已创建 .env');
}

run('pip install', python, ['-m', 'pip', 'install', '-U', 'pip']);
run('python deps', python, ['-m', 'pip', 'install', '-r', 'requirements.txt']);
run('python editable', python, ['-m', 'pip', 'install', '-e', '.[dev,security]']);
run('pnpm install', isWin ? 'pnpm.cmd' : 'pnpm', ['install'], { shell: isWin });

console.log('\n[setup] ✓ 完成 — 下一步: pnpm doctor && pnpm dev\n');
console.log('提示：standalone 模式已只安装核心依赖。');
console.log('      若需 cloud/企业功能（PG/Redis/LDAP/SSO/MFA/向量库）：');
console.log('      pip install -r requirements-optional.txt\n');
