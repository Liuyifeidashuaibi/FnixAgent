"""fnixagent dashboard — 本机 Web 管理台（对标 hermes dashboard :9119）。"""

from __future__ import annotations

import webbrowser
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Fnix Dashboard</title>
<style>
  :root { --bg:#0f1419; --card:#1a2332; --text:#e7ecf3; --muted:#8b9bb4; --accent:#3d9a6a; --border:#2a3548; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: "Segoe UI", system-ui, sans-serif; background: var(--bg); color: var(--text); }
  header { padding: 20px 28px; border-bottom: 1px solid var(--border); display:flex; justify-content:space-between; align-items:center; }
  header h1 { margin:0; font-size:18px; letter-spacing:0.04em; }
  header span { color: var(--muted); font-size:13px; }
  main { max-width: 880px; margin: 0 auto; padding: 24px; display:grid; gap:16px; }
  .card { background: var(--card); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }
  .card h2 { margin:0 0 12px; font-size:15px; }
  label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; }
  input, select { width:100%; padding:10px 12px; border-radius:8px; border:1px solid var(--border); background:#0f1419; color:var(--text); }
  button { margin-top:14px; background:var(--accent); color:#fff; border:0; border-radius:8px; padding:10px 16px; font-weight:600; cursor:pointer; }
  button.secondary { background: transparent; border:1px solid var(--border); color:var(--text); margin-left:8px; }
  .row { display:grid; grid-template-columns: 1fr 1fr; gap:12px; }
  .muted { color:var(--muted); font-size:13px; line-height:1.5; }
  .ok { color:#6dcaa0; } .bad { color:#f0a0a0; }
  pre { white-space:pre-wrap; font-size:12px; color:var(--muted); max-height:220px; overflow:auto; }
  @media (max-width:640px){ .row{grid-template-columns:1fr;} }
</style>
</head>
<body>
<header>
  <h1>Fnix Dashboard</h1>
  <span>本地管理 · 无账号 · BYOK</span>
</header>
<main>
  <div class="card">
    <h2>状态</h2>
    <div id="status" class="muted">加载中…</div>
  </div>
  <div class="card">
    <h2>模型与 API Key</h2>
    <p class="muted">写入 ~/.fnix — 与 Desktop / CLI 同源</p>
    <div class="row">
      <div>
        <label>Provider</label>
        <select id="provider">
          <option value="qwen">Qwen</option>
          <option value="openai">OpenAI</option>
          <option value="deepseek">DeepSeek</option>
          <option value="glm">GLM</option>
          <option value="custom">Custom</option>
        </select>
      </div>
      <div>
        <label>Model</label>
        <input id="model" placeholder="qwen-plus"/>
      </div>
    </div>
    <label>Base URL（可选）</label>
    <input id="base_url" placeholder="https://…"/>
    <label>API Key</label>
    <input id="api_key" type="password" placeholder="留空则不修改已有 Key"/>
    <div>
      <button onclick="saveConfig()">保存</button>
      <button class="secondary" onclick="testLlm()">测试连接</button>
    </div>
    <p id="msg" class="muted"></p>
  </div>
  <div class="card">
    <h2>Sessions</h2>
    <pre id="sessions">…</pre>
  </div>
</main>
<script>
async function api(path, opts){
  const r = await fetch(path, opts);
  const j = await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(j.detail || r.statusText);
  return j;
}
async function refresh(){
  const s = await api('/api/status');
  document.getElementById('status').innerHTML =
    `<div class="${s.ok?'ok':'bad'}">${s.ok?'就绪':'异常'}</div>` +
    `<div>home: ${s.home}</div>` +
    `<div>provider: ${s.provider||'-'} / ${s.model||'-'}</div>` +
    `<div>api_key: ${s.key_hint||'(未设置)'}</div>`;
  document.getElementById('provider').value = s.provider || 'qwen';
  document.getElementById('model').value = s.model || '';
  document.getElementById('base_url').value = s.base_url || '';
  const sess = await api('/api/sessions');
  document.getElementById('sessions').textContent = JSON.stringify(sess.items||[], null, 2);
}
async function saveConfig(){
  const body = {
    provider: document.getElementById('provider').value,
    model: document.getElementById('model').value,
    base_url: document.getElementById('base_url').value,
  };
  const key = document.getElementById('api_key').value.trim();
  if(key) body.api_key = key;
  try {
    await api('/api/config', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    document.getElementById('msg').textContent = '已保存到 ~/.fnix';
    document.getElementById('msg').className = 'ok';
    document.getElementById('api_key').value = '';
    await refresh();
  } catch(e){
    document.getElementById('msg').textContent = e.message;
    document.getElementById('msg').className = 'bad';
  }
}
async function testLlm(){
  const body = {
    provider: document.getElementById('provider').value,
    model: document.getElementById('model').value,
    base_url: document.getElementById('base_url').value,
    api_key: document.getElementById('api_key').value.trim(),
  };
  if(!body.api_key){
    document.getElementById('msg').textContent = '测试需要填写 API Key';
    document.getElementById('msg').className = 'bad';
    return;
  }
  try {
    const r = await api('/api/llm/test', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
    document.getElementById('msg').textContent = '连接成功: ' + (r.preview||'ok');
    document.getElementById('msg').className = 'ok';
  } catch(e){
    document.getElementById('msg').textContent = e.message;
    document.getElementById('msg').className = 'bad';
  }
}
refresh().catch(e => document.getElementById('status').textContent = e.message);
</script>
</body>
</html>
"""


class ConfigBody(BaseModel):
    provider: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


class LlmTestBody(BaseModel):
    provider: str | None = None
    model: str | None = ""
    base_url: str | None = None
    api_key: str = Field(..., min_length=1)


def create_dashboard_app() -> FastAPI:
    app = FastAPI(title="Fnix Dashboard", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return DASHBOARD_HTML

    @app.get("/api/status")
    async def status() -> dict[str, Any]:
        from fnixagent.harness.config import read_config_toml
        from fnixagent.harness.paths import fnix_home
        from fnixagent.harness.secrets import secrets_status
        from fnixagent.harness.workspace import ensure_home_layout

        ensure_home_layout()
        cfg = read_config_toml()
        sec = secrets_status()
        return {
            "ok": True,
            "home": str(fnix_home()),
            "provider": cfg.get("provider", ""),
            "model": cfg.get("model", ""),
            "base_url": cfg.get("base_url", ""),
            **sec,
        }

    @app.put("/api/config")
    async def put_config(body: ConfigBody) -> dict[str, Any]:
        from fnixagent.harness.config import read_config_toml, write_config_toml
        from fnixagent.harness.secrets import secrets_status, set_llm_api_key

        current = read_config_toml()
        if body.provider is not None:
            current["provider"] = body.provider
        if body.model is not None:
            current["model"] = body.model
        if body.base_url is not None:
            current["base_url"] = body.base_url
        write_config_toml(current)
        if body.api_key is not None:
            set_llm_api_key(body.api_key)
        return {"ok": True, **current, **secrets_status()}

    @app.get("/api/sessions")
    async def sessions() -> dict[str, Any]:
        try:
            from fnixagent.harness.session import get_session_store

            store = get_session_store()
            items = store.list_sessions(limit=30) if hasattr(store, "list_sessions") else []
            if not isinstance(items, list):
                items = []
            # serialize lightly
            out = []
            for it in items[:30]:
                if isinstance(it, dict):
                    out.append(
                        {
                            k: it.get(k)
                            for k in ("id", "title", "workspace", "mode", "status", "updated_at")
                            if k in it
                        }
                    )
                else:
                    out.append({"id": getattr(it, "id", str(it))})
            return {"ok": True, "items": out}
        except Exception as e:
            return {"ok": True, "items": [], "note": str(e)}

    @app.post("/api/llm/test")
    async def llm_test(body: LlmTestBody) -> dict[str, Any]:
        from fnixagent.core.llm.adapter import LLMAdapter

        adapter = LLMAdapter(
            api_key=body.api_key.strip(),
            base_url=(body.base_url or "").strip(),
            model_name=(body.model or "").strip(),
            provider_name=(body.provider or "").strip(),
        )
        if not adapter.is_configured:
            raise HTTPException(400, "LLM 未配置")
        try:
            result = await adapter.chat(
                [{"role": "user", "content": "Reply with exactly: ok"}],
                max_tokens=16,
                temperature=0,
            )
            content = ""
            choices = result.get("choices") or []
            if choices:
                content = str((choices[0].get("message") or {}).get("content") or "")[:120]
            return {"ok": True, "preview": content or "connected"}
        except Exception as e:
            raise HTTPException(400, str(e)) from e

    return app


def run_dashboard(*, host: str = "127.0.0.1", port: int = 9119, open_browser: bool = True) -> None:
    import uvicorn

    from fnixagent.harness.workspace import ensure_home_layout

    ensure_home_layout()
    url = f"http://{host}:{port}"
    print(f"\nFnix Dashboard → {url}")
    print("与 Desktop / CLI 共享 ~/.fnix\n")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    uvicorn.run(create_dashboard_app(), host=host, port=port, log_level="info")
