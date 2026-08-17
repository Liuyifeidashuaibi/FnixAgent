#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Curated Work/Code quality gate for Beta CI.
 *
 * Default (no LLM): validate curated Code seed manifest + Work golden scenes.
 * Live (optional):  GATE_FCS_LIVE=1 runs agent against curated seeds with
 *                   --min-hard-pass (default 70).
 *
 * Exit non-zero on any failure — never soft-pass empty/broken benches.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const py = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');

function fail(msg) {
  console.error(`[gate-fcs] ✗ ${msg}`);
  process.exit(1);
}

function ok(msg) {
  console.log(`[gate-fcs] ✓ ${msg}`);
}

function run(label, cmd, args, opts = {}) {
  console.log(`\n[gate-fcs] ▶ ${label}`);
  const r = spawnSync(cmd, args, {
    cwd: root,
    env: { ...process.env, ...opts.env },
    stdio: 'inherit',
    encoding: 'utf-8',
    shell: opts.shell ?? false,
  });
  if (r.status !== 0) {
    fail(`${label} (exit ${r.status ?? 1})`);
  }
  ok(label);
}

// ── Code curated manifest ──────────────────────────────────────────────
const curatedManifest = path.join(root, 'benchmarks/code/curated/manifest.json');
if (!fs.existsSync(curatedManifest)) {
  fail(`missing ${curatedManifest}`);
}
const curated = JSON.parse(fs.readFileSync(curatedManifest, 'utf-8'));
const tasks = curated.tasks || [];
if (tasks.length < 9) {
  fail(`curated Code tasks < 9 (got ${tasks.length})`);
}
for (const tid of tasks) {
  const seed = path.join(root, 'benchmarks/code/seed', `${tid}.json`);
  if (!fs.existsSync(seed)) {
    fail(`curated task missing seed file: ${tid}`);
  }
}
ok(`curated Code manifest (${tasks.length} seeds)`);

run('code validate-only', py, [
  path.join(root, 'scripts/run-code-benchmark.py'),
  '--manifest', curatedManifest,
  '--benchmark-root', path.join(root, 'benchmarks/code'),
  '--limit', '0',
  '--min-tasks', String(tasks.length),
  '--validate-only',
]);

// ── Work golden scenes ─────────────────────────────────────────────────
const goldenDir = path.join(root, 'benchmarks/work/golden');
const goldenFiles = fs
  .readdirSync(goldenDir)
  .filter((f) => f.endsWith('.json'));
if (goldenFiles.length < 10) {
  fail(`Work golden scenes < 10 (got ${goldenFiles.length})`);
}
const goldenErrors = [];
for (const f of goldenFiles) {
  const p = path.join(goldenDir, f);
  try {
    const j = JSON.parse(fs.readFileSync(p, 'utf-8'));
    if (!j.id) goldenErrors.push(`${f}: missing id`);
    if (!j.prompt) goldenErrors.push(`${f}: missing prompt`);
    if (!j.expect_glob) goldenErrors.push(`${f}: missing expect_glob`);
  } catch (e) {
    goldenErrors.push(`${f}: ${e.message || e}`);
  }
}
if (goldenErrors.length) {
  for (const e of goldenErrors) console.error(`  - ${e}`);
  fail('Work golden validation failed');
}
ok(`Work golden scenes (${goldenFiles.length})`);

// ── Optional live FCS + Work golden (needs agentd + BYOK) ──────────────
function loadDotEnv() {
  const envPath = path.join(root, '.env');
  if (!fs.existsSync(envPath)) return;
  for (const line of fs.readFileSync(envPath, 'utf-8').split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith('#') || !t.includes('=')) continue;
    const i = t.indexOf('=');
    const k = t.slice(0, i).trim();
    const v = t.slice(i + 1).trim();
    if (k && process.env[k] === undefined) process.env[k] = v;
  }
}

loadDotEnv();

if (process.env.GATE_FCS_LIVE === '1') {
  const hasKey = Boolean(
    (process.env.DASHSCOPE_API_KEY || '').trim() ||
      (process.env.OPENAI_API_KEY || '').trim(),
  );
  if (!hasKey) {
    fail(
      'GATE_FCS_LIVE=1 requires DASHSCOPE_API_KEY or OPENAI_API_KEY (set in .env or shell)',
    );
  }
  const minHp = process.env.GATE_FCS_MIN_HARD_PASS || String(curated.min_hard_pass_live || 70);
  const base =
    process.env.FNIX_API_BASE ||
    process.env.VITE_API_BASE ||
    process.env.FNIXAGENT_BACKEND_URL ||
    'http://127.0.0.1:8003';

  run('code curated live', py, [
    path.join(root, 'scripts/run-code-benchmark.py'),
    '--manifest', curatedManifest,
    '--benchmark-root', path.join(root, 'benchmarks/code'),
    '--limit', '0',
    '--min-tasks', String(tasks.length),
    '--min-hard-pass', minHp,
    '--base', base,
    '--label', 'curated-live',
  ]);

  const workLimit = process.env.GATE_WORK_GOLDEN_LIMIT || '0';
  const workMinPass = process.env.GATE_WORK_GOLDEN_MIN_PASS || '8';
  run('work golden live', py, [
    path.join(root, 'scripts/e2e-work-golden.py'),
    '--base', base,
    '--limit', workLimit,
    '--min-pass', workMinPass,
  ], {
    env: {
      GATE_FCS_LIVE: '1',
      VITE_API_BASE: base,
      FNIX_API_BASE: base,
    },
  });
} else {
  console.log('\n[gate-fcs] ○ skip live FCS / Work golden (set GATE_FCS_LIVE=1 to enable)');
}

// Offline Work openability (no LLM)
run('work openability offline', py, [
  path.join(root, 'scripts/gate-work-openability.py'),
]);

console.log('\n[gate-fcs] ═══ Curated quality gate passed ═══');
