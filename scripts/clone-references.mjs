#!/usr/bin/env node
/**
 * 克隆全部参考仓库到 _references/（只读借鉴，不提交 git）
 *
 * - Tier A：Harness / Agent UI 主参考（sparse 大仓）
 * - Tier B：FNIX-SE / Office 参考
 * - 最多 7 次重试 + 指数退避；sparse 失败时降级全量浅克隆
 *
 * 用法: pnpm refs:clone
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const destRoot = path.join(root, '_references');
const isWin = process.platform === 'win32';
const MAX_ATTEMPTS = 7;

/** @type {[string, string, 'A'|'B'][]} */
const REPOS = [
  // Tier A — Harness 主参考
  ['openharness', 'https://github.com/HKUDS/OpenHarness.git', 'A'],
  ['goose', 'https://github.com/aaif-goose/goose.git', 'A'],
  ['ag-ui', 'https://github.com/ag-ui-protocol/ag-ui.git', 'A'],
  ['openhands-sdk', 'https://github.com/OpenHands/software-agent-sdk.git', 'A'],
  ['aider', 'https://github.com/Aider-AI/aider.git', 'A'],
  ['mcp-servers', 'https://github.com/modelcontextprotocol/servers.git', 'A'],
  ['copilotkit', 'https://github.com/CopilotKit/CopilotKit.git', 'A'],
  ['pi-mono', 'https://github.com/badlogic/pi-mono.git', 'A'],
  // Tier B — Office / 工具链
  ['grok-build', 'https://github.com/xai-org/grok-build.git', 'B'],
  ['markitdown', 'https://github.com/microsoft/markitdown.git', 'B'],
  ['Office-Word-MCP-Server', 'https://github.com/GongRzhe/Office-Word-MCP-Server.git', 'B'],
  ['OfficeBench', 'https://github.com/zlwang-cs/OfficeBench.git', 'B'],
  ['SpreadsheetBench', 'https://github.com/RUCKBReasoning/SpreadsheetBench.git', 'B'],
  ['open-office-agent', 'https://github.com/tungns2408/open-office-agent.git', 'B'],
  ['unstructured', 'https://github.com/Unstructured-IO/unstructured.git', 'B'],
];

/** sparse checkout 路径（cone 模式用 leading /） */
const SPARSE = {
  'ag-ui': ['/sdks/typescript', '/README.md'],
  copilotkit: ['/CopilotKit', '/skills', '/README.md'],
  goose: ['/documentation', '/ui', '/crates', '/README.md'],
  'grok-build': ['/crates', '/README.md'],
  markitdown: ['/packages/markitdown', '/README.md'],
  unstructured: ['/unstructured', '/README.md'],
};

/** 健康检查：至少存在这些路径之一（数组内 OR）或全部（默认 every） */
const HEALTH = {
  'ag-ui': { paths: ['sdks/typescript'], mode: 'every' },
  copilotkit: { paths: ['skills', 'CopilotKit'], mode: 'some' },
  goose: { paths: ['crates'], mode: 'every' },
  'grok-build': { paths: ['crates', 'README.md'], mode: 'some' },
  markitdown: { paths: ['packages/markitdown', 'README.md'], mode: 'some' },
  unstructured: { paths: ['unstructured', 'README.md'], mode: 'some' },
};

fs.mkdirSync(destRoot, { recursive: true });

function configureGit() {
  const cfg = [
    ['core.longpaths', 'true'],
    ['http.version', 'HTTP/1.1'],
    ['http.postBuffer', '524288000'],
    ['http.lowSpeedLimit', '1000'],
    ['http.lowSpeedTime', '600'],
  ];
  for (const [k, v] of cfg) {
    spawnSync('git', ['config', '--global', k, v], { stdio: 'ignore', shell: isWin });
  }
}

configureGit();

function runGit(args, opts = {}) {
  return spawnSync('git', args, {
    encoding: 'utf-8',
    shell: isWin,
    env: { ...process.env, GIT_TERMINAL_PROMPT: '0' },
    ...opts,
  });
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function isHealthy(name, dest) {
  if (!fs.existsSync(path.join(dest, '.git'))) return false;
  const rule = HEALTH[name];
  if (!rule) return true;
  const checks = rule.paths.map((rel) => fs.existsSync(path.join(dest, rel)));
  return rule.mode === 'some' ? checks.some(Boolean) : checks.every(Boolean);
}

function rmDest(dest) {
  if (fs.existsSync(dest)) {
    fs.rmSync(dest, { recursive: true, force: true, maxRetries: 3 });
  }
}

function cloneFull(url, dest) {
  return runGit(['clone', '--depth', '1', url, dest], { stdio: 'inherit' });
}

function cloneSparse(url, dest, sparsePaths) {
  const r = runGit(['clone', '--depth', '1', '--filter=blob:none', '--sparse', url, dest], {
    stdio: 'inherit',
  });
  if (r.status !== 0) return r;
  return runGit(['-C', dest, 'sparse-checkout', 'set', '--no-cone', ...sparsePaths], {
    stdio: 'inherit',
  });
}

function cloneRepo(name, url, attempt = 1, forceSparse = true) {
  const dest = path.join(destRoot, name);
  const sparsePaths = forceSparse ? SPARSE[name] : null;

  rmDest(dest);

  console.log(`[refs] clone ${name}${attempt > 1 ? ` (retry ${attempt})` : ''}${forceSparse && sparsePaths ? ' [sparse]' : ''}...`);

  let r;
  if (sparsePaths) {
    r = cloneSparse(url, dest, sparsePaths);
  } else {
    r = cloneFull(url, dest);
  }

  if (r.status !== 0) return false;
  return isHealthy(name, dest);
}

const pins = [];
const failed = [];

for (const [name, url, tier] of REPOS) {
  const dest = path.join(destRoot, name);

  if (isHealthy(name, dest)) {
    console.log(`[refs] skip ${name} (ok)`);
    const rev = runGit(['-C', dest, 'rev-parse', 'HEAD']);
    if (rev.stdout) pins.push({ name, url, tier, head: rev.stdout.trim() });
    continue;
  }

  if (fs.existsSync(dest)) {
    console.log(`[refs] repair ${name} (incomplete)`);
  }

  let ok = false;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    ok = cloneRepo(name, url, attempt, true);
    if (ok) break;
    if (SPARSE[name] && attempt === Math.ceil(MAX_ATTEMPTS / 2)) {
      console.warn(`[refs] ${name}: sparse failed, trying full shallow clone...`);
      ok = cloneRepo(name, url, attempt, false);
      if (ok) break;
    }
    if (attempt < MAX_ATTEMPTS) {
      const wait = Math.min(30000, 2000 * 2 ** (attempt - 1));
      console.warn(`[refs] retry ${name} in ${wait / 1000}s...`);
      sleep(wait);
    }
  }

  if (!ok) {
    console.error(`[refs] FAIL ${name}`);
    failed.push(name);
    continue;
  }

  const rev = runGit(['-C', dest, 'rev-parse', 'HEAD']);
  pins.push({ name, url, tier, head: (rev.stdout || '').trim() });
}

const cloneMd = [
  '# Reference clone pins',
  '',
  `Updated: ${new Date().toISOString()}`,
  '',
  '| Repo | Tier | HEAD |',
  '|------|------|------|',
  ...pins.map((p) => `| ${p.name} | ${p.tier} | \`${p.head}\` |`),
  '',
  failed.length ? `Failed: ${failed.join(', ')}` : `All ${pins.length} repos OK.`,
  '',
  'Re-run: `pnpm refs:clone` · Verify: `pnpm refs:verify`',
].join('\n');

fs.writeFileSync(path.join(destRoot, 'CLONE.md'), cloneMd, 'utf-8');

console.log(`\n[refs] ${pins.length}/${REPOS.length} cloned, ${failed.length} failed`);
if (failed.length) {
  console.error(`[refs] Failed: ${failed.join(', ')}`);
  process.exit(1);
}
console.log('[refs] Done. See _references/CLONE.md');
