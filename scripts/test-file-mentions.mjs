/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * L3 自动化：@file 提及解析（与 fileMentions.ts 逻辑对齐）
 */
function extractFileMentions(text) {
  const found = [];
  const re = /(?:^|[\s\n])@([^\s@]+)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const rel = (m[1] || '').replace(/[.,;:!?)]+$/, '');
    if (!rel || rel.includes('..')) continue;
    if (!found.includes(rel)) found.push(rel);
  }
  return found;
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

assert(
  JSON.stringify(extractFileMentions('请看 @src/main.ts 和 @README.md')) ===
    JSON.stringify(['src/main.ts', 'README.md']),
  'basic mentions',
);
assert(extractFileMentions('no mentions here').length === 0, 'empty');
assert(extractFileMentions('bad @../etc/passwd').length === 0, 'reject ..');
assert(
  extractFileMentions('@apps/desktop/src/a.ts').includes('apps/desktop/src/a.ts'),
  'start of string',
);

console.log('[ok] fileMentions L3 checks passed');
