#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** Standalone 冒烟：profile 模块 + 可选 /health */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function run(label, cmd, args, env = {}) {
  const r = spawnSync(cmd, args, {
    cwd: root,
    env: { ...process.env, PYTHONPATH: path.join(root, 'src'), ...env },
    shell: isWin,
    encoding: 'utf-8',
  });
  if (r.status !== 0) {
    console.error(`[smoke] FAIL ${label}`);
    if (r.stdout) process.stdout.write(r.stdout);
    if (r.stderr) process.stderr.write(r.stderr);
    process.exit(r.status ?? 1);
  }
  console.log(`[smoke] OK ${label}`);
}

run('pytest profile', python, ['-m', 'pytest', 'tests/unit/test_profile.py', '-q']);
run('pytest harness', python, [
  '-m',
  'pytest',
  'tests/unit/test_harness.py',
  'tests/unit/test_harness_config.py',
  'tests/unit/test_harness_index.py',
  'tests/integration/test_standalone_harness.py',
  '-q',
]);
run('pytest fnix-local', python, ['-m', 'pytest', 'tests/unit/test_local_sidecar.py', '-q']);
run('pytest work mission', python, ['-m', 'pytest', 'tests/unit/test_work_mission_schema.py', '-q']);

const healthUrl = process.env.SMOKE_HEALTH_URL || 'http://127.0.0.1:8003/health';
try {
  const res = await fetch(healthUrl);
  if (res.ok) {
    const data = await res.json();
    console.log('[smoke] OK health', data);
  } else {
    console.log(`[smoke] SKIP health (${healthUrl} → HTTP ${res.status})`);
  }
} catch {
  console.log(`[smoke] SKIP health (后端未运行，可忽略)`);
}

console.log('[smoke] Standalone 检查完成');
