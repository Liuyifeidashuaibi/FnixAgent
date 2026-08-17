#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** 启动 fnix-local sidecar（Python MVP，默认 127.0.0.1:8710） */
import { spawn } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';

function findFreePort(start = 8710, max = 8720) {
  return new Promise((resolve, reject) => {
    const tryPort = (port) => {
      if (port > max) {
        reject(new Error(`fnix-local 无可用端口 (${start}-${max})`));
        return;
      }
      const server = net.createServer();
      server.once('error', () => tryPort(port + 1));
      server.once('listening', () => {
        server.close(() => resolve(port));
      });
      server.listen(port, '127.0.0.1');
    };
    tryPort(start);
  });
}

const port = Number(process.env.FNIX_LOCAL_PORT) || (await findFreePort());
const host = process.env.FNIX_LOCAL_HOST || '127.0.0.1';
const url = `http://${host}:${port}`;

console.log(`[fnix-local] 启动 sidecar ${url}`);

const child = spawn(
  python,
  ['-m', 'fnixagent.local'],
  {
    cwd: root,
    env: {
      ...process.env,
      PYTHONPATH: path.join(root, 'src'),
      FNIX_LOCAL_HOST: host,
      FNIX_LOCAL_PORT: String(port),
    },
    shell: isWin,
    stdio: 'inherit',
  },
);

child.on('exit', (code) => process.exit(code ?? 0));

process.on('SIGINT', () => child.kill('SIGTERM'));
process.on('SIGTERM', () => child.kill('SIGTERM'));

console.log(`[fnix-local] FNIX_LOCAL_URL=${url}`);
