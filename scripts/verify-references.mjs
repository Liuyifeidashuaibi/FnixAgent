#!/usr/bin/env node
/** 验证 _references/ 克隆完整性 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const destRoot = path.join(root, '_references');

const REQUIRED = [
  'openharness',
  'goose',
  'ag-ui',
  'openhands-sdk',
  'aider',
  'mcp-servers',
  'copilotkit',
  'pi-mono',
  'grok-build',
  'markitdown',
  'Office-Word-MCP-Server',
  'OfficeBench',
  'SpreadsheetBench',
  'open-office-agent',
  'unstructured',
];

let ok = 0;
let fail = 0;

for (const name of REQUIRED) {
  const dest = path.join(destRoot, name);
  const hasGit = fs.existsSync(path.join(dest, '.git'));
  if (hasGit) {
    console.log(`[refs:verify] ✓ ${name}`);
    ok++;
  } else {
    console.error(`[refs:verify] ✗ ${name} missing`);
    fail++;
  }
}

console.log(`[refs:verify] ${ok}/${REQUIRED.length} required repos`);
process.exit(fail ? 1 : 0);
