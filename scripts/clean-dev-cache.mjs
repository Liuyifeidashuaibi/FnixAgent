#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Clean dev caches that commonly fill C: (业界编码工具 sandbox, npm, pip, cargo, project artifacts).
 *
 * Usage:
 *   node scripts/clean-dev-cache.mjs          # safe defaults
 *   node scripts/clean-dev-cache.mjs --aggressive  # also prune pnpm store, old temp
 */
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const aggressive = process.argv.includes('--aggressive');

function rm(dir) {
  if (!dir || !fs.existsSync(dir)) return 0;
  try {
    fs.rmSync(dir, { recursive: true, force: true });
    console.log(`  removed ${dir}`);
    return 1;
  } catch (e) {
    console.warn(`  skip ${dir}: ${e.message}`);
    return 0;
  }
}

function run(cmd) {
  try {
    execSync(cmd, { stdio: 'inherit', shell: true });
  } catch {
    /* optional */
  }
}

const home = os.homedir();
const temp = os.tmpdir();
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

console.log('Fnix dev cache cleanup\n');

// --- C: / system temp (业界编码工具 agent builds can reach 60GB+) ---
const tempTargets = [
  path.join(temp, 'cursor-sandbox-cache'),
  path.join(temp, 'DockerDesktopUpdates'),
];
if (aggressive) {
  // Remove temp entries older than 3 days (top-level only)
  const cutoff = Date.now() - 3 * 864e5;
  for (const name of fs.readdirSync(temp, { withFileTypes: true })) {
    try {
      const full = path.join(temp, name.name);
      const st = fs.statSync(full);
      if (st.mtimeMs < cutoff) tempTargets.push(full);
    } catch {
      /* ignore */
    }
  }
}
for (const t of tempTargets) rm(t);

// --- Package manager caches ---
console.log('\nPackage caches:');
run('pnpm store prune');
if (aggressive) run('npm cache clean --force');
if (aggressive) run('pip cache purge');
if (aggressive) run('cargo cache -a');

// --- Project build artifacts (on repo drive, usually E:) ---
console.log('\nProject artifacts:');
const projectDirs = [
  'apps/desktop-tauri/src-tauri/target',
  'apps/fnix-local/target',
  'node_modules/.cache',
  '.pytest_cache',
  'dist',
  'build',
  'htmlcov',
  '.ruff_cache',
];
for (const rel of projectDirs) rm(path.join(root, rel));

console.log('\nDone. Re-run `pnpm install` if you removed node_modules/.cache.');
