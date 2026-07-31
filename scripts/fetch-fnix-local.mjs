#!/usr/bin/env node
/**
 * 获取 fnix-local 二进制 — Release 下载 / 本地编译 / Python fallback 占位
 *
 * 用法:
 *   node scripts/fetch-fnix-local.mjs [win|mac|linux]
 *   FNIX_LOCAL_RELEASE_URL=https://.../fnix-local-win.zip node scripts/fetch-fnix-local.mjs
 *   FNIX_BUILD_LOCAL=1 node scripts/fetch-fnix-local.mjs
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const node = process.execPath;
const isWin = process.platform === 'win32';

const targets = [
  path.join(root, 'apps', 'workbench', 'src-tauri', 'resources', 'fnix-local'),
];

const platform =
  process.argv[2] ||
  (process.platform === 'win32' ? 'win' : process.platform === 'darwin' ? 'mac' : 'linux');

const RELEASE_URL = process.env.FNIX_LOCAL_RELEASE_URL || '';
const BUILD_LOCAL = process.env.FNIX_BUILD_LOCAL === '1' || process.env.FNIX_BUILD_LOCAL === 'true';

function binaryName() {
  if (platform === 'win') return 'fnix-local.exe';
  return 'fnix-local';
}

function writePlaceholder(reason) {
  const text = `# fnix-local (Rust sidecar)

platform: ${platform}
status: ${reason}

Dev fallback: \`python -m fnixagent.local\`

Build locally:
\`\`\`bash
FNIX_BUILD_LOCAL=1 node scripts/fetch-fnix-local.mjs
# or
node scripts/build-fnix-local.mjs
\`\`\`

Release download:
\`\`\`bash
FNIX_LOCAL_RELEASE_URL=https://github.com/.../releases/download/vX/fnix-local-${platform}.zip
node scripts/fetch-fnix-local.mjs
\`\`\`

See docs/FNIXAI_SIBLING.md
`;
  for (const outDir of targets) {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, 'STATUS.md'), text, 'utf-8');
  }
}

async function downloadAndExtract(url) {
  console.log('[fetch-fnix-local] 下载:', url);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  const tmp = path.join(root, '.tmp-fnix-local.zip');
  fs.writeFileSync(tmp, buf);

  if (isWin) {
    const ps = spawnSync(
      'powershell',
      [
        '-NoProfile',
        '-Command',
        `Expand-Archive -Path '${tmp.replace(/'/g, "''")}' -DestinationPath '${path.join(root, '.tmp-fnix-local').replace(/'/g, "''")}' -Force`,
      ],
      { stdio: 'inherit' },
    );
    if (ps.status !== 0) throw new Error('Expand-Archive failed');
  } else {
    spawnSync('unzip', ['-o', tmp, '-d', path.join(root, '.tmp-fnix-local')], { stdio: 'inherit' });
  }

  const extractDir = path.join(root, '.tmp-fnix-local');
  const found = findBinary(extractDir, binaryName());
  if (!found) throw new Error(`未在 zip 中找到 ${binaryName()}`);

  for (const outDir of targets) {
    fs.mkdirSync(outDir, { recursive: true });
    fs.copyFileSync(found, path.join(outDir, binaryName()));
  }

  fs.rmSync(tmp, { force: true });
  fs.rmSync(extractDir, { recursive: true, force: true });
  console.log('[fetch-fnix-local] 二进制已安装');
}

function findBinary(dir, name) {
  if (!fs.existsSync(dir)) return null;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isFile() && entry.name === name) return full;
    if (entry.isDirectory()) {
      const nested = findBinary(full, name);
      if (nested) return nested;
    }
  }
  return null;
}

console.log('[fetch-fnix-local] platform=', platform);

try {
  if (RELEASE_URL) {
    await downloadAndExtract(RELEASE_URL);
    process.exit(0);
  }

  if (BUILD_LOCAL) {
    const r = spawnSync(node, [path.join(root, 'scripts', 'build-fnix-local.mjs')], {
      cwd: root,
      stdio: 'inherit',
    });
    process.exit(r.status ?? 1);
  }

  // 已有二进制则跳过
  const existing = path.join(targets[0], binaryName());
  if (fs.existsSync(existing)) {
    console.log('[fetch-fnix-local] 已有二进制:', existing);
    process.exit(0);
  }

  writePlaceholder('Python fallback — 未配置 Release / 未本地编译');
  console.log('[fetch-fnix-local] FNIX_LOCAL_RELEASE_URL 未设置 — 使用 Python sidecar');
  console.log('[fetch-fnix-local] 本地编译: FNIX_BUILD_LOCAL=1 node scripts/fetch-fnix-local.mjs');
} catch (e) {
  console.error('[fetch-fnix-local]', e instanceof Error ? e.message : e);
  writePlaceholder(`fetch failed: ${e instanceof Error ? e.message : e}`);
  process.exit(1);
}
