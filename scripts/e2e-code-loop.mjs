#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 全流程闭环自测入口（无需付费 API Key）
 *
 * 覆盖：新建项目 → AI 写码（脚本化 LLM）→ 编译 → 报错修复
 *
 * 用法: pnpm smoke:code-loop
 */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

const child = spawn(
  python,
  ['-m', 'pytest', 'tests/integration/test_code_loop_closed.py', '-q', '--tb=short'],
  {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: path.join(root, 'src'),
      FNIX_CODE_HEAL_ROUNDS: process.env.FNIX_CODE_HEAL_ROUNDS || '2',
    },
    stdio: 'inherit',
    shell: isWin,
  },
);

child.on('exit', (code) => {
  if (code === 0) {
    console.log('[smoke:code-loop] OK — 新建项目→写码→编译→修错 闭环通过');
  } else {
    console.error(`[smoke:code-loop] FAILED exit=${code}`);
  }
  process.exit(code ?? 1);
});
