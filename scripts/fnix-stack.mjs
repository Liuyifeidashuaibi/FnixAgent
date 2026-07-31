#!/usr/bin/env node
/**
 * fnix-stack — Fnix 顶级集成工具
 *
 * 审计参考仓、FnixAi 姊妹仓、sidecar 契约，一键同步与编译。
 *
 * 用法:
 *   node scripts/fnix-stack.mjs audit     # 健康检查 + 复用建议
 *   node scripts/fnix-stack.mjs sync        # refs:clone + verify + FnixAi 检查
 *   node scripts/fnix-stack.mjs sidecar     # 编译 fnix-local（FnixAi 优先）
 *   node scripts/fnix-stack.mjs report      # 写入 docs/STACK_AUDIT.md
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const node = process.execPath;
const isWin = process.platform === 'win32';
const cmd = process.argv[2] || 'audit';

const FNIXAI_ROOT = process.env.FNIXAI_ROOT || process.env.FNIXAI_SIBLING || 'E:\\FNIX\\FnixAi';
const FNIXAI_SE = path.join(FNIXAI_ROOT, 'fnix-se');

/** @type {{ id: string, tier: string, absorb: string, fnixTarget: string }[]} */
const NETWORK_MATRIX = [
  { id: 'openharness', tier: 'A', absorb: 'Harness 布局/skills/session/gateway', fnixTarget: 'src/fnixagent/harness/' },
  { id: 'ag-ui', tier: 'A', absorb: 'AG-UI 事件 schema + HttpAgent', fnixTarget: 'packages/ag-ui-mapper + agent-ui' },
  { id: 'copilotkit', tier: 'A', absorb: 'Tool 卡片 / Generative UI', fnixTarget: 'packages/agent-ui' },
  { id: 'goose', tier: 'A', absorb: 'MCP 配置形态', fnixTarget: 'SettingsPanel Harness' },
  { id: 'openhands-sdk', tier: 'A', absorb: '本地 workspace 执行', fnixTarget: 'core/tools/workspace.py' },
  { id: 'aider', tier: 'A', absorb: 'RepoMap 符号排名', fnixTarget: 'core/code/indexer.py' },
  { id: 'mcp-servers', tier: 'A', absorb: 'MCP 标准 server', fnixTarget: '~/.fnix/mcp.json' },
  { id: 'pi-mono', tier: 'A', absorb: '多平台 agent 模式', fnixTarget: '长期参考' },
  { id: 'grok-build', tier: 'B', absorb: 'Agent loop / tools', fnixTarget: 'core/tools/' },
  { id: 'markitdown', tier: 'B', absorb: '文档→MD', fnixTarget: 'Work 文档工具' },
];

/** @type {{ name: string, relPath: string, reuse: string, priority: 'P0'|'P1'|'P2' }[]} */
const FNIXAI_REUSE = [
  { name: 'fnix-pdg', relPath: 'crates/fnix-pdg/Cargo.toml', reuse: '/v1/index PDG 图', priority: 'P0' },
  { name: 'fnix-ast', relPath: 'crates/fnix-ast/Cargo.toml', reuse: '符号解析', priority: 'P0' },
  { name: 'fnix-vector', relPath: 'crates/fnix-vector/Cargo.toml', reuse: '/v1/context vector_hits', priority: 'P0' },
  { name: 'fnix-tools', relPath: 'crates/fnix-tools/src/run_command.rs', reuse: '/v1/run PTY+blocklist', priority: 'P0' },
  { name: 'fnix-tools-read', relPath: 'crates/fnix-tools/src/read_file.rs', reuse: '/v1/read 安全路径', priority: 'P0' },
  { name: 'fnix-sandbox', relPath: 'crates/fnix-sandbox/Cargo.toml', reuse: '沙箱/PTY', priority: 'P1' },
  { name: 'cli-index', relPath: 'apps/cli/src/main.rs', reuse: 'index 管线', priority: 'P0' },
  { name: 'agent-hooks', relPath: 'apps/cli/src/agent_hooks.rs', reuse: 'context 排名', priority: 'P0' },
  { name: 'fnix-local-app', relPath: 'apps/fnix-local/Cargo.toml', reuse: 'OpenAPI sidecar 壳', priority: 'P0' },
  { name: 'apps-server', relPath: 'apps/server/src/main.rs', reuse: '❌ 非 sidecar 契约', priority: 'P2' },
  { name: 'fnix-ui', relPath: 'crates/fnix-ui/Cargo.toml', reuse: '❌ 保留 FnixAi GPU UI', priority: 'P2' },
  { name: 'fnix-agent-loop', relPath: 'crates/fnix-agent/src/loop_engine.rs', reuse: '❌ Python 大脑已有', priority: 'P2' },
];

function exists(p) {
  try {
    return fs.existsSync(p);
  } catch {
    return false;
  }
}

function run(label, script, env = {}) {
  console.log(`\n[stack] ▶ ${label}`);
  const r = spawnSync(node, [path.join(root, 'scripts', script)], {
    cwd: root,
    env: { ...process.env, ...env },
    stdio: 'inherit',
    shell: isWin,
  });
  return r.status === 0;
}

function sidecarBinary() {
  return isWin ? 'fnix-local.exe' : 'fnix-local';
}

function auditReferences() {
  const refRoot = path.join(root, '_references');
  const rows = [];
  for (const item of NETWORK_MATRIX) {
    const dir = path.join(refRoot, item.id);
    const ok = exists(dir) && fs.readdirSync(dir).length > 0;
    rows.push({ ...item, ok, path: dir });
  }
  return rows;
}

function auditFnixAi() {
  const rows = [];
  for (const item of FNIXAI_REUSE) {
    const full = path.join(FNIXAI_SE, item.relPath);
    rows.push({ ...item, ok: exists(full), path: full });
  }
  const hasFnixLocalApp = exists(path.join(FNIXAI_SE, 'apps/fnix-local/Cargo.toml'));
  return { rows, hasFnixLocalApp, fnixAiRoot: FNIXAI_SE, fnixAiExists: exists(FNIXAI_SE) };
}

function auditSidecar() {
  const targets = [
    path.join(root, 'apps/workbench/src-tauri/resources/fnix-local', sidecarBinary()),
    path.join(root, 'apps/fnix-local/Cargo.toml'),
    path.join(root, 'src/fnixagent/local/sidecar_app.py'),
    path.join(root, 'packages/protocol/openapi/fnix-local-v1.yaml'),
    path.join(root, 'tests/contract/test_fnix_local_openapi.py'),
  ];
  return {
    rustBinary: exists(targets[0]),
    rustBinaryPath: targets[0],
    rustCrate: exists(targets[1]),
    pythonMvp: exists(targets[2]),
    openapi: exists(targets[3]),
    contractTest: exists(targets[4]),
  };
}

function auditAgentUi() {
  return {
    agentUi: exists(path.join(root, 'packages/agent-ui/package.json')),
    agUiMapper: exists(path.join(root, 'packages/ag-ui-mapper/package.json')),
    composerRefactored: exists(path.join(root, 'apps/desktop/src/renderer/ComposerPanel.tsx')),
  };
}

function printAudit() {
  console.log('\n═══════════════════════════════════════════════════');
  console.log('  Fnix Stack Audit — 顶级集成健康检查');
  console.log('═══════════════════════════════════════════════════\n');

  const refs = auditReferences();
  const okRefs = refs.filter((r) => r.ok).length;
  console.log(`📚 网络参考仓 (_references/): ${okRefs}/${refs.length}`);
  for (const r of refs) {
    console.log(`  ${r.ok ? '✓' : '✗'} [${r.tier}] ${r.id.padEnd(16)} → ${r.fnixTarget}`);
  }

  const ai = auditFnixAi();
  console.log(`\n🦀 FnixAi 姊妹仓: ${ai.fnixAiExists ? FNIXAI_SE : '未找到'}`);
  if (ai.fnixAiExists) {
    const reusable = ai.rows.filter((r) => r.priority !== 'P2' && r.ok);
    const missing = ai.rows.filter((r) => r.priority === 'P0' && !r.ok);
    console.log(`  可复用模块: ${reusable.length} · P0 缺失: ${missing.length}`);
    for (const r of ai.rows) {
      if (r.priority === 'P2') continue;
      console.log(`  ${r.ok ? '✓' : '✗'} [${r.priority}] ${r.name.padEnd(18)} ${r.reuse}`);
    }
    console.log(`\n  apps/fnix-local (OpenAPI sidecar): ${ai.hasFnixLocalApp ? '✓ 已存在' : '✗ 待 FnixAi 新建'}`);
    if (!ai.hasFnixLocalApp) {
      console.log('  → 建议: 在 FnixAi fnix-se 创建 apps/fnix-local，复用 fnix-pdg + fnix-tools');
    }
  } else {
    console.log('  设置 FNIXAI_ROOT 环境变量指向姊妹仓');
  }

  const sc = auditSidecar();
  console.log('\n⚡ Sidecar 链');
  console.log(`  OpenAPI 契约:     ${sc.openapi ? '✓' : '✗'}`);
  console.log(`  Python MVP:       ${sc.pythonMvp ? '✓' : '✗'}`);
  console.log(`  Rust 参考实现:    ${sc.rustCrate ? '✓' : '✗'}`);
  console.log(`  Rust 二进制打包:  ${sc.rustBinary ? '✓' : '✗'} ${sc.rustBinary ? sc.rustBinaryPath : ''}`);
  console.log(`  契约测试:         ${sc.contractTest ? '✓' : '✗'}`);

  const ui = auditAgentUi();
  console.log('\n🎨 成熟 UI 栈');
  console.log(`  @fnixagent/agent-ui:  ${ui.agentUi ? '✓' : '✗'}`);
  console.log(`  ag-ui-mapper:         ${ui.agUiMapper ? '✓' : '✗'}`);

  console.log('\n📋 推荐下一步');
  const steps = [];
  if (okRefs < refs.length) steps.push('pnpm refs:clone');
  if (ai.fnixAiExists && !ai.hasFnixLocalApp) steps.push('FnixAi: 新建 apps/fnix-local (见 docs/TOP_TIER_INTEGRATION.md)');
  if (!sc.rustBinary) steps.push('pnpm stack:sidecar');
  steps.push('pnpm check:plan');
  if (!ui.agentUi) steps.push('packages/agent-ui 缺失 — 检查 workspace');
  steps.forEach((s, i) => console.log(`  ${i + 1}. ${s}`));

  console.log('\n═══════════════════════════════════════════════════\n');
  return { refs, ai, sc, ui, ok: okRefs >= 8 && sc.openapi && sc.pythonMvp };
}

function buildSidecar() {
  const fnixAiLocal = path.join(FNIXAI_SE, 'apps/fnix-local/Cargo.toml');
  if (exists(fnixAiLocal)) {
    console.log('[stack] FnixAi apps/fnix-local 存在 — 优先编译姊妹仓');
    process.env.FNIXAI_ROOT = FNIXAI_ROOT;
    const ok = run('build from FnixAi', 'build-fnix-local.mjs');
    if (ok) return true;
    console.warn('[stack] FnixAi 编译失败 — fallback 本仓');
  }
  delete process.env.FNIXAI_ROOT;
  return run('build local fnix-local', 'build-fnix-local.mjs');
}

function generateReport(result) {
  const { refs, ai, sc, ui } = result;
  const lines = [
    '# Fnix Stack Audit Report',
    '',
    `> 自动生成：${new Date().toISOString()}`,
    `> 命令：\`pnpm stack:report\``,
    '',
    '## 参考仓',
    '',
    '| 仓 | Tier | 状态 | 吸收 | Fnix 落点 |',
    '|----|------|------|------|-----------|',
    ...refs.map((r) => `| ${r.id} | ${r.tier} | ${r.ok ? '✓' : '✗'} | ${r.absorb} | ${r.fnixTarget} |`),
    '',
    '## FnixAi 姊妹仓',
    '',
    `路径: \`${FNIXAI_SE}\` · 存在: ${ai.fnixAiExists ? '是' : '否'}`,
    '',
    '| 模块 | P | 状态 | 用途 |',
    '|------|---|------|------|',
    ...ai.rows.map((r) => `| ${r.name} | ${r.priority} | ${r.ok ? '✓' : '✗'} | ${r.reuse} |`),
    '',
    `**apps/fnix-local**: ${ai.hasFnixLocalApp ? '已存在' : '待新建'}`,
    '',
    '## Sidecar',
    '',
    `- OpenAPI: ${sc.openapi ? '✓' : '✗'}`,
    `- Python MVP: ${sc.pythonMvp ? '✓' : '✗'}`,
    `- Rust crate: ${sc.rustCrate ? '✓' : '✗'}`,
    `- Rust binary: ${sc.rustBinary ? '✓' : '✗'}`,
    `- Contract tests: ${sc.contractTest ? '✓' : '✗'}`,
    '',
    '## UI 栈',
    '',
    `- agent-ui: ${ui.agentUi ? '✓' : '✗'}`,
    `- ag-ui-mapper: ${ui.agUiMapper ? '✓' : '✗'}`,
    '',
    '## 行动项',
    '',
    '1. 保持 `_references/` 只读 — 不 import 进产品',
    '2. FnixAi 新建 `apps/fnix-local` 接入 fnix-pdg/fnix-tools',
    '3. AG-UI 适配器连接 FastAPI NDJSON → 前端',
    '4. OpenHarness session/skills 模式持续吸收',
    '',
    '详见 [TOP_TIER_INTEGRATION.md](./TOP_TIER_INTEGRATION.md)',
    '',
  ];
  const out = path.join(root, 'docs/STACK_AUDIT.md');
  fs.writeFileSync(out, lines.join('\n'), 'utf-8');
  console.log(`[stack] 报告已写入 ${out}`);
}

function sync() {
  let ok = true;
  ok = run('refs:clone', 'clone-references.mjs') && ok;
  ok = run('refs:verify', 'verify-references.mjs') && ok;
  printAudit();
  return ok;
}

switch (cmd) {
  case 'audit':
    printAudit();
    break;
  case 'sync':
    if (!sync()) process.exit(1);
    break;
  case 'sidecar':
    if (!buildSidecar()) process.exit(1);
    printAudit();
    break;
  case 'report': {
    const result = printAudit();
    generateReport(result);
    break;
  }
  default:
    console.log(`用法: node scripts/fnix-stack.mjs <audit|sync|sidecar|report>`);
    process.exit(1);
}
