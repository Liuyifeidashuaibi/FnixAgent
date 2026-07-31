#!/usr/bin/env node
/**
 * Mega Plan 验收 — 对照 docs/MEGA_PLAN.md 自动检查可验证项
 *
 * 用法: pnpm check:plan
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const node = process.execPath;
const python = isWin ? 'python' : 'python3';

const results = [];

function record(id, label, ok, detail = '') {
  results.push({ id, label, ok, detail });
  const mark = ok ? '✓' : '✗';
  console.log(`[plan] ${mark} ${label}${detail ? ` — ${detail}` : ''}`);
}

function runPytest(args, label) {
  const r = spawnSync(python, ['-m', 'pytest', ...args], {
    cwd: root,
    env: { ...process.env, PYTHONPATH: path.join(root, 'src') },
    encoding: 'utf-8',
  });
  record(label, label, r.status === 0, r.status === 0 ? '' : 'pytest failed');
  return r.status === 0;
}

function runNode(script, label, env = {}) {
  const r = spawnSync(node, [path.join(root, 'scripts', script)], {
    cwd: root,
    env: { ...process.env, ...env },
    encoding: 'utf-8',
    stdio: 'pipe',
  });
  record(label, label, r.status === 0, r.status === 0 ? '' : (r.stderr || r.stdout || '').slice(0, 120));
  return r.status === 0;
}

console.log('[plan] Fnix v1.0 Mega Plan — 自动验收\n');

// 1. pytest harness + local
runPytest(
  [
    'tests/unit/test_harness.py',
    'tests/unit/test_harness_config.py',
    'tests/unit/test_harness_index.py',
    'tests/unit/test_local_sidecar.py',
    'tests/integration/test_standalone_harness.py',
    'tests/unit/test_chat_agent_apply.py',
    'tests/unit/test_ag_ui_mapper.py',
    'tests/contract/test_fnix_local_openapi.py',
    '-q',
  ],
  'pytest harness + integration',
);

runNode('e2e-full.mjs', 'e2e:full harness flow');
runNode('verify-references.mjs', 'refs:verify (10 required repos)');

// 2. verify-beta (含 e2e:standalone)
runNode('verify-beta.mjs', 'pnpm verify:beta', { SKIP_E2E_STANDALONE: '0' });

// 3. sidecar runtime（e2e:standalone 已覆盖，单独再验）
runNode('e2e-standalone.mjs', 'sidecar /health runtime=python');

// 4. 文件/脚本存在性
const mustExist = [
  'apps/workbench/src-tauri/src/runtime.rs',
  'apps/workbench/src-tauri/src/secure.rs',
  'apps/workbench/src-tauri/src/pty_manager.rs',
  'apps/workbench/src/shell/chatgpt-desktop/ProcessTimeline.tsx',
  'apps/workbench/src/shell/chatgpt-desktop/WorkTaskBar.tsx',
  'apps/workbench/src/shell/chatgpt-desktop/fnixRuntime.ts',
  'apps/workbench/src/shell/chatgpt-desktop/OnboardingWizard.tsx',
  'apps/workbench/src/ui/glass/index.ts',
  'apps/fnix-local/Cargo.toml',
  'scripts/build-fnix-local.mjs',
  'playwright.config.ts',
  'e2e/ui/login.spec.ts',
  'scripts/e2e-full.mjs',
  'scripts/verify-references.mjs',
  'scripts/dev-all-tauri.mjs',
  'scripts/e2e-standalone.mjs',
  '.github/workflows/release.yml',
  'docs/BETA_RELEASE.md',
  'docs/HARNESS_PLAN_v1.0.md',
  'scripts/sync-plan-to-desktop.mjs',
];
for (const rel of mustExist) {
  const full = path.join(root, rel);
  record(rel, `exists ${rel}`, fs.existsSync(full));
}

// 5. 需人工项（记录为 skip）
const manual = [
  ['ui-work-code', 'Work + Code UI 各完成一次真实 LLM 任务', '需 BYOK + 手动点验'],
  ['pty-ui', 'Tauri PTY Tab 交互', '需 Tauri Desktop 手动点验'],
  ['keychain-ui', 'Token 存 OS Keychain', '需 Tauri 登录后检查'],
  ['release-tag', 'git tag v1.0.0-beta.1 → GitHub Release', '需 push tag'],
  ['demo-gif', 'Demo GIF', '需录屏'],
  ['rust-sidecar', 'Rust fnix-local 二进制', 'FnixAi Release 未发布'],
  ['tauri-build-win', 'Windows 本地 tauri build', '需 MSVC 工具链'],
];
console.log('\n[plan] 需人工 / 外部依赖:');
for (const [, label, why] of manual) {
  console.log(`  ○ ${label} — ${why}`);
}

const failed = results.filter((r) => !r.ok);
console.log(`\n[plan] 自动项: ${results.length - failed.length}/${results.length} 通过`);
if (failed.length) {
  console.error('[plan] FAIL', failed.map((f) => f.label).join(', '));
  process.exit(1);
}
console.log('[plan] 所有可自动验收项已通过');
