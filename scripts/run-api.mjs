#!/usr/bin/env node
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
