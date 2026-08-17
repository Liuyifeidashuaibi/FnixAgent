#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * 将 fnixagent Python 源码复制到 Tauri Desktop resources（Release / dev 打包）
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const srcRoot = path.join(root, 'src', 'fnixagent');
const destRoot = path.join(
  root,
  'apps',
  'workbench',
  'src-tauri',
  'resources',
  'fnixagent-py',
  'src',
  'fnixagent',
);

function copyDir(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    const src = path.join(from, entry.name);
    const dst = path.join(to, entry.name);
    if (entry.isDirectory()) {
      // 跳过 __pycache__ 和 .pytest_cache 等缓存目录
      if (entry.name === '__pycache__' || entry.name === '.pytest_cache' || entry.name === '.mypy_cache') continue;
      copyDir(src, dst);
    } else if (entry.name.endsWith('.pyc') || entry.name.endsWith('.pyo')) {
      // 跳过编译后的 Python 文件
      continue;
    } else {
      // 复制 .py 及所有数据文件 (.json, .yaml, .txt, .jinja2, .toml 等)
      fs.copyFileSync(src, dst);
    }
  }
}

if (!fs.existsSync(srcRoot)) {
  console.error('[bundle-python] missing', srcRoot);
  process.exit(1);
}

const bundleDir = path.dirname(path.dirname(destRoot));
fs.rmSync(path.join(bundleDir, 'src'), { recursive: true, force: true });
copyDir(srcRoot, destRoot);
const marker = path.join(bundleDir, 'BUNDLE.txt');
fs.mkdirSync(bundleDir, { recursive: true });
fs.writeFileSync(
  marker,
  `Bundled at ${new Date().toISOString()}\nSource: ${srcRoot}\nDest: ${destRoot}\n`,
  'utf-8',
);
console.log('[bundle-python] copied →', bundleDir);
