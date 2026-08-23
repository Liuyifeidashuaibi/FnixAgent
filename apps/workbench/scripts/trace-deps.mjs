/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

// Trace real dependency graph from production entry points.
// Usage: node scripts/trace-deps.mjs
import fs from 'node:fs';
import path from 'node:path';

const SRC = path.resolve(process.cwd(), 'src');
const exts = ['.ts', '.tsx', '.js', '.jsx', '.css', '.json'];

function resolveImport(fromFile, spec) {
  if (!spec.startsWith('.')) return null; // package import
  const base = path.resolve(path.dirname(fromFile), spec);
  const candidates = [
    base,
    ...exts.map((e) => base + e),
    ...exts.map((e) => path.join(base, 'index' + e)),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c) && fs.statSync(c).isFile()) return c;
  }
  return null;
}

const importRe = /(?:import|export)\s+(?:[^'"]*?\s+from\s+)?["']([^"']+)["']/g;
const dynImportRe = /import\(\s*["']([^"']+)["']\s*\)/g;
const cssImportRe = /@import\s+["']([^"']+)["']/g;

function scan(file) {
  let text;
  try {
    text = fs.readFileSync(file, 'utf8');
  } catch {
    return [];
  }
  const out = [];
  for (const re of [importRe, dynImportRe, cssImportRe]) {
    re.lastIndex = 0;
    let m;
    while ((m = re.exec(text))) out.push(m[1]);
  }
  return out;
}

// Production entries: main.tsx static imports + DesktopApp (dynamic prod path)
const entries = [path.join(SRC, 'main.tsx'), path.join(SRC, 'shell/desktop/DesktopApp.tsx')];
// Excluded dynamic branches (dev/test): App.tsx, GlassKitPreview, Spec3Preview
const EXCLUDE = new Set([
  path.join(SRC, 'App.tsx'),
  path.join(SRC, 'Spec3Preview.tsx'),
  path.join(SRC, 'ui/glass/preview/GlassKitPreview.tsx'),
]);

const seen = new Set();
const queue = [...entries];
while (queue.length) {
  const f = queue.pop();
  if (!f || seen.has(f) || EXCLUDE.has(f)) continue;
  seen.add(f);
  for (const spec of scan(f)) {
    const r = resolveImport(f, spec);
    if (r && r.startsWith(SRC) && !seen.has(r) && !EXCLUDE.has(r)) queue.push(r);
  }
}

// All source files
function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|css)$/.test(e.name)) out.push(p);
  }
  return out;
}
const all = walk(SRC);
const used = all.filter((f) => seen.has(f));
const dead = all.filter((f) => !seen.has(f));

console.log(`TOTAL ${all.length}  USED ${used.length}  DEAD ${dead.length}`);
console.log('\n=== DEAD FILES (not reachable from production shell) ===');
for (const f of dead.sort()) console.log(path.relative(SRC, f));
fs.writeFileSync(
  'scripts/dead-files.txt',
  dead
    .sort()
    .map((f) => path.relative(SRC, f))
    .join('\n'),
);
