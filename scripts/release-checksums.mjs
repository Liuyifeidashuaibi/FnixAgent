#!/usr/bin/env node
/**
 * Generate SHA-256 checksums (+ minimal SBOM stub) for release artifacts.
 *
 * Usage:
 *   node scripts/release-checksums.mjs [dir]
 * Default dir: apps/workbench/src-tauri/target/release/bundle
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const target = path.resolve(process.argv[2] || path.join(root, 'apps/workbench/src-tauri/target/release/bundle'));

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (/\.(exe|msi|dmg|app\.tar\.gz|deb|AppImage|nsis\.zip)$/i.test(entry.name) || entry.name.endsWith('.exe')) {
      out.push(full);
    }
  }
  return out;
}

function sha256(file) {
  const hash = crypto.createHash('sha256');
  hash.update(fs.readFileSync(file));
  return hash.digest('hex');
}

if (!fs.existsSync(target)) {
  console.warn('[checksums] directory missing:', target);
  console.warn('[checksums] skip (build bundle first)');
  process.exit(0);
}

const files = walk(target);
if (!files.length) {
  // Also checksum sidecar binaries used by packaging.
  const sidecars = [
    path.join(root, 'apps/workbench/src-tauri/resources/agentd', process.platform === 'win32' ? 'fnix-agentd.exe' : 'fnix-agentd'),
  ].filter((p) => fs.existsSync(p));
  if (!sidecars.length) {
    console.warn('[checksums] no artifacts found');
    process.exit(0);
  }
  files.push(...sidecars);
}

const lines = [];
const sbom = {
  bomFormat: 'CycloneDX',
  specVersion: '1.5',
  version: 1,
  metadata: {
    timestamp: new Date().toISOString(),
    component: { type: 'application', name: 'fnix', version: process.env.npm_package_version || '0.0.0' },
  },
  components: [],
};

for (const file of files) {
  const digest = sha256(file);
  const rel = path.relative(root, file).replace(/\\/g, '/');
  lines.push(`${digest}  ${rel}`);
  sbom.components.push({
    type: 'file',
    name: path.basename(file),
    version: process.env.npm_package_version || '0.0.0',
    hashes: [{ alg: 'SHA-256', content: digest }],
  });
}

const outDir = path.join(root, 'dist-release');
fs.mkdirSync(outDir, { recursive: true });
const sumPath = path.join(outDir, 'SHA256SUMS.txt');
const sbomPath = path.join(outDir, 'sbom.cdx.json');
fs.writeFileSync(sumPath, `${lines.join('\n')}\n`, 'utf-8');
fs.writeFileSync(sbomPath, JSON.stringify(sbom, null, 2), 'utf-8');
console.log('[checksums] wrote', sumPath);
console.log('[checksums] wrote', sbomPath);
console.log(`[checksums] ${files.length} file(s)`);
