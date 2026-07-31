#!/usr/bin/env node
/**
 * Build a self-contained agentd one-folder sidecar with PyInstaller.
 *
 * Output: apps/workbench/src-tauri/resources/agentd/
 * Fallback: when PyInstaller is missing, keep Python source bundle only.
 *
 * Usage: node scripts/build-agentd-sidecar.mjs
 *        SKIP_PYINSTALLER=1 node scripts/build-agentd-sidecar.mjs  # copy-only
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const isWin = process.platform === 'win32';
const python = isWin ? 'python' : 'python3';
const outDir = path.join(root, 'apps', 'workbench', 'src-tauri', 'resources', 'agentd');
const workDir = path.join(root, 'packaging', '.pyinstaller');
const entry = path.join(root, 'packaging', 'agentd_entry.py');
const name = 'fnix-agentd';

function run(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, {
    cwd: opts.cwd || root,
    env: { ...process.env, PYTHONPATH: path.join(root, 'src'), ...opts.env },
    stdio: 'inherit',
    // Only shell for pnpm.cmd-style launchers; never for python -c / PyInstaller.
    shell: Boolean(opts.shell),
  });
  return r.status ?? 1;
}

function hasPyInstaller() {
  // Avoid shell:true — on Windows it breaks `python -c "import ..."`.
  const r = spawnSync(
    python,
    ['-c', 'import PyInstaller; print(PyInstaller.__version__)'],
    { cwd: root, encoding: 'utf-8' },
  );
  return r.status === 0;
}

// Always refresh the source copy used for development / fallback.
const copyStatus = run(process.execPath, [path.join(root, 'scripts/bundle-python-runtime.mjs')]);
if (copyStatus !== 0) process.exit(copyStatus);

if (process.env.SKIP_PYINSTALLER === '1') {
  console.log('[agentd-sidecar] SKIP_PYINSTALLER=1 — source bundle only');
  process.exit(0);
}

if (!hasPyInstaller()) {
  console.warn('[agentd-sidecar] PyInstaller not installed; keeping .py source bundle.');
  console.warn('[agentd-sidecar] Install with: pip install pyinstaller');
  process.exit(0);
}

fs.rmSync(workDir, { recursive: true, force: true });
fs.rmSync(outDir, { recursive: true, force: true });
fs.mkdirSync(workDir, { recursive: true });
fs.mkdirSync(outDir, { recursive: true });

const args = [
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--onedir',
  '--name',
  name,
  '--distpath',
  path.join(workDir, 'dist'),
  '--workpath',
  path.join(workDir, 'build'),
  '--specpath',
  workDir,
  '--paths',
  path.join(root, 'src'),
  '--hidden-import',
  'fnixagent',
  '--hidden-import',
  'uvicorn',
  '--hidden-import',
  'fastapi',
  entry,
];

console.log('[agentd-sidecar] building with PyInstaller…');
const status = run(python, args);
if (status !== 0) {
  console.error('[agentd-sidecar] PyInstaller failed');
  process.exit(status);
}

const built = path.join(workDir, 'dist', name);
if (!fs.existsSync(built)) {
  console.error('[agentd-sidecar] missing build output', built);
  process.exit(1);
}

fs.cpSync(built, outDir, { recursive: true });
const marker = path.join(outDir, 'BUNDLE.txt');
fs.writeFileSync(
  marker,
  `fnix-agentd PyInstaller bundle\nBuilt: ${new Date().toISOString()}\nHost: ${process.platform}-${process.arch}\n`,
  'utf-8',
);
console.log('[agentd-sidecar] wrote', outDir);
