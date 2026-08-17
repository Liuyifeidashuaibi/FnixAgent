#!/usr/bin/env node
/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * API 冒烟 — harness + work + sidecar（需 agentd + sidecar 已运行）
 * 自包含版: pnpm e2e:standalone
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const base = process.env.VITE_API_BASE || process.env.fnixagent_BACKEND_URL || 'http://127.0.0.1:8003';
const localBase = process.env.FNIX_LOCAL_URL || 'http://127.0.0.1:8710';

async function main() {
  const health = await fetch(`${base}/health`);
  if (!health.ok) throw new Error(`health failed: ${health.status}`);
  const healthJson = await health.json();
  console.log('[e2e] agentd profile:', healthJson.profile ?? healthJson);

  try {
    const sidecar = await fetch(`${localBase}/health`);
    if (sidecar.ok) {
      const sj = await sidecar.json();
      console.log('[e2e] sidecar:', sj.service, sj.runtime ?? 'python');
    }
  } catch {
    console.log('[e2e] sidecar: offline (optional)');
  }

  const status = await fetch(`${base}/api/v1/harness/status`);
  if (!status.ok) throw new Error(`harness status failed: ${status.status}`);
  const statusJson = await status.json();
  console.log('[e2e] harness:', statusJson.ok ? 'ok' : statusJson);

  const workStatus = await fetch(`${base}/api/v1/work/status`);
  if (!workStatus.ok) throw new Error(`work status failed: ${workStatus.status}`);
  console.log('[e2e] work pipeline ready:', (await workStatus.json()).ktg);

  const tmp = path.join(root, 'data', 'e2e-workspace');
  fs.mkdirSync(tmp, { recursive: true });

  const ensure = await fetch(`${base}/api/v1/harness/workspace/ensure`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace: tmp }),
  });
  console.log('[e2e] workspace ensure:', ensure.ok);

  const index = await fetch(`${base}/api/v1/harness/index`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workspace: tmp, force: false }),
  });
  const indexJson = await index.json();
  console.log('[e2e] index:', index.ok ? 'ok' : index.status, indexJson.ok ?? indexJson);

  const sessions = await fetch(`${base}/api/v1/work/sessions?limit=5`);
  if (!sessions.ok) throw new Error(`sessions failed: ${sessions.status}`);
  const sessionsJson = await sessions.json();
  console.log('[e2e] sessions:', Array.isArray(sessionsJson.sessions) ? sessionsJson.sessions.length : 0);

  console.log('[e2e] PASS');
}

main().catch((e) => {
  console.error('[e2e] FAIL', e.message || e);
  process.exit(1);
});
