#!/usr/bin/env node
/**
 * v1.0 Beta 验收 — 单元测试 + 前端 typecheck + Rust compile
 *
 * 用法:
 *   pnpm verify:beta
 *   SMOKE_WITH_API=1 pnpm verify:beta   # 额外跑 e2e:api（需 agentd 运行）
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { tauriCargoEnv, tauriCrateDir } from './fnix-cargo-env.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';

function run(label, cmd, args, opts = {}) {
  console.log(`\n[verify] ▶ ${label}`);
  const useShell = opts.shell ?? false;
  const r = spawnSync(cmd, args, {
    cwd: opts.cwd || root,
    env: { ...process.env, ...opts.env },
    shell: useShell,
    stdio: 'inherit',
    encoding: 'utf-8',
  });
  if (r.status !== 0) {
    console.error(`[verify] ✗ FAIL ${label}`);
    process.exit(r.status ?? 1);
  }
  console.log(`[verify] ✓ ${label}`);
}

const node = process.execPath;

// 1. Python 单元测试（Harness / sidecar / profile）
run('smoke:standalone', node, [path.join(root, 'scripts/smoke-standalone.mjs')]);

// 2. 捆绑 Python 资源（Tauri 编译需要 glob 匹配）
if (process.env.SKIP_VERIFY_BUNDLE !== '1') {
  run('bundle:python', node, [path.join(root, 'scripts/bundle-python-runtime.mjs')]);
} else {
  console.log('\n[verify] ○ skip bundle:python (SKIP_VERIFY_BUNDLE=1)');
}

// 3. 默认 Workbench renderer typecheck（与发布壳相同）
run('typecheck workbench', isWin ? 'pnpm.cmd' : 'pnpm', [
  '--filter',
  '@fnixagent/workbench',
  'typecheck',
], { shell: isWin });

// 4. Rust compile（隔离 target，防 FnixAi CARGO_TARGET_DIR 污染）
run('cargo check', 'cargo', ['check'], {
  cwd: tauriCrateDir(),
  env: tauriCargoEnv(),
});

// 5. Standalone 端到端（自动 spawn 进程）
if (process.env.SKIP_E2E_STANDALONE !== '1') {
  run('e2e:standalone', node, [path.join(root, 'scripts/e2e-standalone.mjs')]);
} else {
  console.log('\n[verify] ○ skip e2e:standalone (SKIP_E2E_STANDALONE=1)');
}

// 6. 可选：对已运行 API 冒烟
if (process.env.SMOKE_WITH_API === '1') {
  run('e2e:api', node, [path.join(root, 'scripts/e2e-api-smoke.mjs')]);
} else {
  console.log('\n[verify] ○ skip e2e:api (set SMOKE_WITH_API=1 to enable)');
}

// 7. Curated Work/Code quality gate（validate-only；live 用 GATE_FCS_LIVE=1）
if (process.env.SKIP_GATE_FCS !== '1') {
  run('gate:fcs', node, [path.join(root, 'scripts/gate-curated-fcs.mjs')]);
} else {
  console.log('\n[verify] ○ skip gate:fcs (SKIP_GATE_FCS=1)');
}

console.log('\n[verify] ═══ Beta 验收通过 ═══');
