#!/usr/bin/env node
/**
 * 全链路模拟：模拟用户从前端开始使用 FnixAgent，并验证项目内各环节是否真正发挥作用。
 * 阶段 1：真实 Chrome 加载前端 (5175) → 验证渲染 + 捕获「前端→后端」真实网络调用 + 控制台错误。
 * 阶段 2：按 OpenAPI tag 遍历后端所有子系统（无鉴权），再 owner 登录后复测受保护子系统。
 * 阶段 3：真实流式对话（/api/v1/chat/stream），以 BYOK key 驱动 agent loop + LLM，验证真正返回内容。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const API = process.env.FNIX_API_BASE || 'http://127.0.0.1:8003';
const FE = process.env.FNIX_FE_BASE || 'http://127.0.0.1:5175';
const outDir = path.join(root, '.fnix-smoke-test');
fs.mkdirSync(outDir, { recursive: true });

const results = { browser: null, routersOpen: [], routersGated: [], auth: null, realChat: null, summary: {} };

// 解析 .env 中需要的密钥（不打印）。用 indexOf 解析以避开 CRLF/正则边界问题。
function loadEnv() {
  const env = {};
  try {
    const txt = fs.readFileSync(path.join(root, '.env'), 'utf8');
    for (const raw of txt.split('\n')) {
      const i = raw.indexOf('=');
      if (i <= 0) continue;
      const k = raw.slice(0, i).trim();
      if (!/^[A-Z0-9_]+$/.test(k)) continue;
      let v = raw.slice(i + 1).replace(/\r$/, '').trim();
      if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) v = v.slice(1, -1);
      env[k] = v;
    }
  } catch {}
  return env;
}
const ENV = loadEnv();

async function req(method, url, body, auth, timeoutMs = 5000) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const opts = { method, headers: { Accept: 'application/json' }, signal: ctrl.signal };
    if (auth) opts.headers['Authorization'] = 'Bearer ' + auth;
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const r = await fetch(url, opts);
    let text = ''; try { text = await r.text(); } catch {}
    return { status: r.status, ok: r.ok, text: text.slice(0, 240) };
  } catch (e) {
    return { status: 0, ok: false, text: 'ERR ' + (e.name === 'AbortError' ? 'timeout' : e.message) };
  } finally { clearTimeout(t); }
}

// ----------------------------- 阶段 1：前端浏览器 -----------------------------
async function phaseBrowser() {
  let browser;
  try {
    const { chromium } = await import('@playwright/test');
    browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-gpu'] });
  } catch (e) {
    return { ok: false, error: 'playwright/chrome 不可用: ' + e.message, consoleErrors: [], apiCalls: [], rendered: false };
  }
  const page = await browser.newPage();
  const consoleErrors = [];
  const apiCalls = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => consoleErrors.push('PAGEERROR ' + e.message.slice(0, 200)));
  page.on('response', (res) => { const u = res.url(); if (u.includes('/api')) apiCalls.push({ url: u.replace(FE, '<FE>'), status: res.status() }); });
  try {
    await page.goto(FE, { waitUntil: 'domcontentloaded', timeout: 25000 });
    await page.waitForFunction(() => { const r = document.getElementById('root'); return r && r.childElementCount > 0; }, { timeout: 15000 }).catch(() => {});
    const info = await page.evaluate(() => ({ title: document.title, rootChildren: document.getElementById('root')?.childElementCount ?? 0, bodyTextLen: document.body.innerText.length }));
    const shot = path.join(outDir, 'sim_frontend.png');
    await page.screenshot({ path: shot, fullPage: false });
    await browser.close();
    const rendered = info.rootChildren > 0 && info.bodyTextLen > 50;
    const proxied = await req('GET', `${FE}/health`);
    const apiOk = apiCalls.filter((c) => c.status >= 200 && c.status < 400).length;
    return { ok: true, rendered, title: info.title, rootChildren: info.rootChildren, bodyTextLen: info.bodyTextLen, screenshot: shot, consoleErrors: consoleErrors.slice(0, 12), proxyHealth: proxied.status, apiCallsCaptured: apiCalls.length, apiCallsOk: apiOk, apiCallsSample: apiCalls.slice(0, 8) };
  } catch (e) {
    try { await browser.close(); } catch {}
    return { ok: false, error: e.message, consoleErrors: consoleErrors.slice(0, 12), apiCalls: apiCalls.slice(0, 8), rendered: false };
  }
}

// ----------------------------- 阶段 2a：开放子系统 + 2b：受保护子系统(带 token) -----------------------------
async function phaseRouters(token) {
  const spec = await (await fetch(`${API}/openapi.json`)).json();
  const paths = spec.paths || {};
  const byTag = {};
  for (const p of Object.keys(paths)) {
    for (const m of Object.keys(paths[p])) {
      if (!['get', 'post', 'put', 'delete', 'patch'].includes(m)) continue;
      const tag = paths[p][m].tags?.[0] || 'untagged';
      (byTag[tag] ||= []).push({ p, m });
    }
  }
  const pick = (ops) => { let x = ops.find((o) => o.m === 'get' && !o.p.includes('{')); if (!x) x = ops[0]; return x; };
  const open = [], gated = [];
  for (const [tag, ops] of Object.entries(byTag)) {
    const o = pick(ops);
    const method = o.m.toUpperCase();
    const body = ['POST', 'PUT', 'DELETE'].includes(method) ? {} : undefined;
    const r = await req(method, `${API}${o.p}`, body, token);
    const entry = { subsystem: tag, path: o.p, method, status: r.status, reachable: r.status !== 404 && r.status !== 0, functional: r.status >= 200 && r.status < 300, note: r.text.replace(/\n/g, ' ').slice(0, 100) };
    if (token && r.status === 401) gated.push(entry); // 带 token 仍 401 的，记为未通过鉴权
    else if (!token && r.status === 401) gated.push(entry); // 无 token 时 401 = 受保护
    else open.push(entry);
  }
  open.sort((a, b) => b.functional - a.functional);
  gated.sort((a, b) => b.functional - a.functional);
  return { open, gated };
}

// ----------------------------- 阶段 2c：owner 登录 -----------------------------
async function phaseAuth() {
  const ownerToken = ENV.FNIX_OWNER_TOKEN || 'fnix-owner-local-2026';
  const username = ENV.FNIX_OWNER_USERNAME || 'admin';
  // 不截断返回体，以免 JWT 被切断导致解析失败
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 8000);
  let full = '';
  try {
    const r = await fetch(`${API}/api/v1/auth/owner/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: 'sim-pass-' + Date.now(), owner_token: ownerToken, client_uuid: 'sim' }),
      signal: ctrl.signal,
    });
    full = await r.text();
    if (!r.ok) return { ok: false, status: r.status, note: full.slice(0, 200), token: null };
    const j = JSON.parse(full);
    return { ok: true, status: r.status, token: j.access_token || null, username };
  } catch (e) {
    return { ok: false, status: 0, note: (full || e.message).slice(0, 200), token: null };
  } finally { clearTimeout(t); }
}

// ----------------------------- 阶段 3：真实流式对话（BYOK）-----------------------------
async function phaseRealChat() {
  const key = ENV.DASHSCOPE_API_KEY || '';
  const url = `${API}/api/v1/chat/stream`;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 90000);
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ user_input: '用一句话介绍你自己，并说明你能帮我做什么。', session_id: 1, llm: { provider: 'qwen', model: 'qwen-plus', api_key: key } }),
      signal: ctrl.signal,
    });
    if (!r.ok || !r.body) return { ok: false, status: r.status, body: (await r.text()).slice(0, 300), content: '' };
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = '', textContent = '', errMsg = '', sawDone = false, firstChunkMs = null, chunks = 0;
    const t0 = Date.now();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n'); buf = lines.pop();
      for (const line of lines) {
        let s = line.trim();
        if (!s) continue;
        if (s.startsWith('data:')) s = s.slice(5).trim();
        if (!s) continue;
        if (s === '[DONE]') { sawDone = true; continue; }
        try {
          const ev = JSON.parse(s);
          if (ev.chunk_type === 'error') { errMsg = (ev.content || errMsg); continue; } // 错误事件不计入正文
          if (typeof ev.content === 'string' && ev.content) { if (firstChunkMs == null) firstChunkMs = Date.now() - t0; textContent += ev.content; chunks++; }
          if (ev.done) sawDone = true;
        } catch {}
      }
    }
    clearTimeout(t);
    const ok = textContent.length > 0 && !errMsg;
    return { ok, status: r.status, contentChars: textContent.length, contentChunks: chunks, firstChunkMs, sawDone, errMsg, contentSample: textContent.slice(0, 260) };
  } catch (e) {
    clearTimeout(t);
    return { ok: false, reason: e.name === 'AbortError' ? 'timeout(90s)' : e.message, content: '' };
  }
}

// ----------------------------- 运行 -----------------------------
async function main() {
  console.log('=== 阶段 1：前端浏览器加载 ===');
  results.browser = await phaseBrowser();
  console.log(JSON.stringify(results.browser, null, 2));

  console.log('\n=== 阶段 2a：子系统遍历（无鉴权）===');
  const { open, gated } = await phaseRouters(null);
  results.routersOpen = open;
  for (const r of open) console.log(`[${r.functional ? 'OK ' : 'WARN'}] ${String(r.subsystem).padEnd(14)} ${r.method} ${r.path} -> ${r.status}`);

  console.log('\n=== 阶段 2c：owner 登录（获取 admin token）===');
  results.auth = await phaseAuth();
  console.log(JSON.stringify({ ...results.auth, token: results.auth.token ? '<redacted>' : null }, null, 2));

  if (results.auth.token) {
    console.log('\n=== 阶段 2b：受保护子系统复测（带 admin token）===');
    const g2 = await phaseRouters(results.auth.token);
    results.routersGated = g2.open.concat(g2.gated); // 带 token 后这些应变为 open
    for (const r of results.routersGated) console.log(`[${r.functional ? 'OK ' : 'FAIL'}] ${String(r.subsystem).padEnd(14)} ${r.method} ${r.path} -> ${r.status}`);
  } else {
    console.log('\n（无 admin token，受保护子系统维持 401 状态，记为其鉴权链路存在）');
    results.routersGated = gated;
  }

  console.log('\n=== 阶段 3：真实流式对话（BYOK key 驱动 agent loop + LLM）===');
  results.realChat = await phaseRealChat();
  console.log(JSON.stringify(results.realChat, null, 2));

  const allRouters = results.routersOpen.concat(results.routersGated);
  const fn = allRouters.filter((r) => r.functional).length;
  const reach = allRouters.filter((r) => r.reachable).length;
  results.summary = {
    browserRendered: results.browser?.rendered === true,
    browserConsoleErrors: (results.browser?.consoleErrors || []).length,
    browserApiCallsCaptured: results.browser?.apiCallsCaptured || 0,
    browserApiCallsOk: results.browser?.apiCallsOk || 0,
    subsystemsTotal: allRouters.length,
    subsystemsReachable: reach,
    subsystemsFunctional: fn,
    adminTokenObtained: results.auth?.ok === true,
    realChatOk: results.realChat?.ok === true,
    realChatChars: results.realChat?.contentChars || 0,
  };
  console.log('\n=== 汇总 ===');
  console.log(JSON.stringify(results.summary, null, 2));
  const reportPath = path.join(outDir, 'sim_user_journey.json');
  fs.writeFileSync(reportPath, JSON.stringify(results, null, 2));
  console.log(`\n报告已写入: ${reportPath}`);
}

main().catch((e) => { console.error('FATAL', e); process.exit(1); });
