#!/usr/bin/env node
/**
 * archive-dev-artifacts.mjs — 仓库根目录开发产物归档（opt-in，需手动运行）。
 *
 * 把散落在根目录的调试/评测产物移入 .temp/archive/<日期>/：
 *   - bench_*.log / *_bench*.log / backend_*.log / frontend_dev*.log
 *   - *.png 截图（仅根目录）
 *   - _*.py / diag_*.py / probe_*.py / ui_*.py / _q_*.py 临时探针脚本
 *   - bench_*_results*.jsonl
 *
 * 用法:
 *   node scripts/archive-dev-artifacts.mjs [--dry-run]
 *
 * 不触碰: 源码、配置、文档、.env*、package.json 等白名单外的一切常规文件。
 */

import { readdirSync, mkdirSync, renameSync, statSync } from "node:fs";
import { join, basename } from "node:path";

const ROOT = process.cwd();
const dryRun = process.argv.includes("--dry-run");
const stamp = new Date().toISOString().slice(0, 10);
const DEST = join(ROOT, ".temp", "archive", stamp);

// 归档规则（仅匹配根目录文件名）
const PATTERNS = [
  /^bench[_-].*\.(log|py|jsonl)$/i,
  /^.*_bench.*\.log$/i,
  /^(backend|frontend)_.*(log\d*)\.(log|txt)?$/i,
  /\.(log)$/i,
  /^(diag|probe|ui_recon|ui_write_site|ui_poll|verify_interface)[^\/]*\.py$/i,
  /^_[a-zA-Z0-9_]+\.py$/, // _q_done.py / _bench2.py 等下划线前缀临时脚本
  /^test[^\/]*\.(png)$/i,
  /^(screenshot|work-home|workspace-|sidebar-|code-home|final-result|attach-menu|analysis-expanded|typewriter|nastasia|ui_\d|hello\.txt)/i,
];

const KEEP = new Set([
  "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml",
  "pyproject.toml", "requirements.txt", "requirements-optional.txt", "uv.lock",
  "alembic.ini", "Makefile", "LICENSE", "NOTICE", "README.md", "CHANGELOG.md",
  ".env", ".env.example",
]);

function matches(name) {
  if (KEEP.has(name) || name.startsWith(".")) return false;
  if (/\.(md|html|yml|yaml|toml|json|cjs|ts|svg|docx)$|^(Makefile|LICENSE|NOTICE)/i.test(name)) {
    // 文档/报告/配置不归档，除非明确命中 log/png 规则
    if (!/\.(png|log|jsonl)$/i.test(name)) return false;
  }
  return PATTERNS.some((re) => re.test(name));
}

const moved = [];
for (const name of readdirSync(ROOT)) {
  const full = join(ROOT, name);
  let st;
  try { st = statSync(full); } catch { continue; }
  if (!st.isFile()) continue;
  if (matches(name)) moved.push({ from: full, to: join(DEST, basename(name)) });
}

if (moved.length === 0) {
  console.log("[archive] 根目录没有可归档的开发产物。");
  process.exit(0);
}

console.log(`[archive] 发现 ${moved.length} 个文件${dryRun ? "（dry-run 预览）" : ""}:`);
for (const m of moved) console.log(`  ${m.from.replace(ROOT, "")} → ${m.to.replace(ROOT, "")}`);

if (!dryRun) {
  mkdirSync(DEST, { recursive: true });
  for (const m of moved) {
    try { renameSync(m.from, m.to); } catch (e) { console.warn(`  [skip] ${basename(m.from)}: ${e.message}`); }
  }
  console.log(`[archive] 完成 → .temp/archive/${stamp}/`);
}
