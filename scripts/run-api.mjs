#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** 仅启动 Python API（Standalone） */
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';

spawn(isWin ? 'python' : 'python3', ['-m', 'fnixagent.main', 'serve', '--host', '127.0.0.1'], {
  cwd: root,
  env: {
    ...process.env,
    PYTHONPATH: path.join(root, 'src'),
    FNIXAGENT_PROFILE: process.env.FNIXAGENT_PROFILE || 'standalone',
  },
  shell: isWin,
  stdio: 'inherit',
});
