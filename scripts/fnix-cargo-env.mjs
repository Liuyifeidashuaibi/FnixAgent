/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * MSVC environment for Windows Tauri builds.
 */
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const tauriTargetDir = path.join(root, 'apps', 'workbench', 'src-tauri', 'target');

export function tauriCargoEnv(extra = {}) {
  const env = { ...process.env, ...extra };
  env.CARGO_TARGET_DIR = tauriTargetDir;
  if (os.platform() === 'win32') {
    env.CARGO_BUILD_TARGET = 'x86_64-pc-windows-msvc';
  }
  return env;
}

export function tauriCrateDir() {
  return path.join(root, 'apps', 'workbench', 'src-tauri');
}

export function sidecarCargoEnv(crateDir, extra = {}) {
  const env = { ...process.env, ...extra };
  env.CARGO_TARGET_DIR = path.join(crateDir, 'target');
  return env;
}

export function findVcvars64() {
  const pf = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
  const vswhere = path.join(pf, 'Microsoft Visual Studio', 'Installer', 'vswhere.exe');
  if (!fs.existsSync(vswhere)) return null;
  try {
    const installPath = execSync(
      `"${vswhere}" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`,
      { encoding: 'utf-8' },
    ).trim();
    if (!installPath) return null;
    const vcvars = path.join(installPath, 'VC', 'Auxiliary', 'Build', 'vcvars64.bat');
    return fs.existsSync(vcvars) ? vcvars : null;
  } catch {
    return null;
  }
}

/** Merge MSVC PATH/libs from vcvars64 into env (avoids cmd line length limits). */
export function msvcDevEnv(extra = {}) {
  const base = tauriCargoEnv(extra);
  if (os.platform() !== 'win32') return base;
  const vcvars = findVcvars64();
  if (!vcvars) return base;
  try {
    const out = execSync(`cmd /c "\"${vcvars}\" >nul 2>&1 && set"`, {
      encoding: 'utf-8',
      maxBuffer: 10 * 1024 * 1024,
    });
    for (const line of out.split(/\r?\n/)) {
      const i = line.indexOf('=');
      if (i <= 0) continue;
      base[line.slice(0, i)] = line.slice(i + 1);
    }
  } catch {
    /* keep base */
  }
  return base;
}

export function detectWindowsMsvc() {
  if (os.platform() !== 'win32') return { ok: true, reason: 'non-windows' };
  const vcvars = findVcvars64();
  if (vcvars) return { ok: true, path: vcvars };
  return {
    ok: false,
    reason: '未检测到 Visual Studio Build Tools（Tauri Windows 需要 MSVC）',
    hint: 'winget install Microsoft.VisualStudio.2022.BuildTools',
  };
}
