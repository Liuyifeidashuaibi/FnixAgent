/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Minimal Desktop-look Settings — local BYOK + model name (no model catalog).
 */

import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Eye, EyeOff, KeyRound, Loader2 } from "lucide-react";
import type { AppConfig } from "../../utils/tauri";
import { saveAIProviders, saveConfigToStore } from "../../utils/tauri";
import { testConnection, type AIProviderConfig } from "../../utils/providers";
import {
  approveMcpTrust,
  denyMcpTrust,
  fetchHarnessStatus,
  fetchMemorySearch,
  fetchMemoryStats,
  fetchSkillsList,
  fetchSkillDrafts,
  createSkillDraft,
  submitSkillForReview,
  approveSkill,
  deprecateSkill,
  listMcpTrust,
  pingAgentd,
  runRuntimeDoctor,
  syncHarnessConfig,
  testHarnessLlm,
  cleanupMemory,
  type FnixRuntimeDoctorReport,
  type FnixMemoryStats,
  type FnixMemoryItem,
  type FnixSkillEntry,
  type FnixSkillStatus,
  type McpTrustServerRow,
} from "../../lib/fnixBridge";
import { LOCAL_LLM, localProviderConfig } from "./localLlm";
import { normalizeThemePref } from "./theme";
import "./DesktopSettings.css";

type Section = "general" | "models" | "about" | "diagnostics" | "mcp" | "memory" | "skills";

interface Props {
  config: AppConfig;
  providers: AIProviderConfig[];
  onConfigChange: (c: AppConfig) => void;
  onProvidersChange: (p: AIProviderConfig[]) => void;
  onClose: () => void;
  initialSection?: Section;
  onOpenBenchmark?: () => void;
  projectPath?: string;
}

function ensureLocalProvider(providers: AIProviderConfig[]): AIProviderConfig {
  const existing =
    providers.find((p) => p.id === "local-dashscope") ||
    providers.find((p) => p.apiKey?.trim()) ||
    providers[0];
  if (existing) return existing;
  return localProviderConfig();
}

export function DesktopSettings({
  config,
  providers,
  onConfigChange,
  onProvidersChange,
  onClose,
  initialSection = "models",
  onOpenBenchmark,
  projectPath = "",
}: Props) {
  const [section, setSection] = useState<Section>(initialSection);
  const seed = ensureLocalProvider(providers);
  const [apiKey, setApiKey] = useState(seed.apiKey || config.api_key || LOCAL_LLM.apiKey);
  const [model, setModel] = useState(
    seed.models.find((m) => m.enabled)?.id || seed.models[0]?.id || config.model || LOCAL_LLM.model,
  );
  const [baseUrl, setBaseUrl] = useState(seed.baseUrl || LOCAL_LLM.baseUrl);
  const [showKey, setShowKey] = useState(false);
  const [doctor, setDoctor] = useState<FnixRuntimeDoctorReport | null>(null);
  const [doctorBusy, setDoctorBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [mcpServers, setMcpServers] = useState<McpTrustServerRow[]>([]);
  const [mcpBusy, setMcpBusy] = useState(false);
  const [mcpError, setMcpError] = useState<string | null>(null);

  // Memory (S1.2.4)
  const [memStats, setMemStats] = useState<FnixMemoryStats | null>(null);
  const [memQuery, setMemQuery] = useState("");
  const [memUserId, setMemUserId] = useState("desktop");
  const [memItems, setMemItems] = useState<FnixMemoryItem[]>([]);
  const [memBusy, setMemBusy] = useState(false);
  const [memError, setMemError] = useState<string | null>(null);

  // Skills (S1.2.3)
  const [skillEntries, setSkillEntries] = useState<FnixSkillEntry[]>([]);
  const [skillFilter, setSkillFilter] = useState<FnixSkillStatus | "all">("all");
  const [skillBusy, setSkillBusy] = useState(false);
  const [skillError, setSkillError] = useState<string | null>(null);
  const [skillNewName, setSkillNewName] = useState("");
  const [skillNewDesc, setSkillNewDesc] = useState("");

  // Diagnostics — 5 red/yellow/green cards
  type DocColor = "green" | "yellow" | "red";
  interface DocCardState {
    color: DocColor;
    title: string;
    detail?: string;
  }
  const [docAgentd, setDocAgentd] = useState<DocCardState | null>(null);
  const [docLlmKey, setDocLlmKey] = useState<DocCardState | null>(null);
  const [docHome, setDocHome] = useState<DocCardState | null>(null);
  const [docWorkspace, setDocWorkspace] = useState<DocCardState | null>(null);
  const [docSidecar, setDocSidecar] = useState<DocCardState | null>(null);

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      // 1. agentd
      const alive = await pingAgentd({ timeoutMs: 4000 });
      if (cancelled) return;
      setDocAgentd(
        alive
          ? { color: "green", title: "agentd 已就绪" }
          : {
              color: "red",
              title: "agentd 离线",
              detail: "启动命令：python -m uvicorn fnixagent.main:app --port 8003",
            },
      );

      // 3 + 5. harness status (~/.fnix + sidecar)
      const st = await fetchHarnessStatus();
      if (cancelled) return;
      const homeExists = st?.home_dir?.exists;
      if (typeof homeExists === "boolean") {
        setDocHome(
          homeExists
            ? { color: "green", title: "~/.fnix 存在", detail: st?.home_dir?.path }
            : { color: "red", title: "~/.fnix 不存在", detail: "请启动 agentd 以初始化 home 目录" },
        );
      } else {
        setDocHome({
          color: "red",
          title: "~/.fnix 不存在",
          detail: "agentd 未响应，无法检测 home 目录",
        });
      }
      const sidecarAvail = st?.sidecar?.available;
      if (typeof sidecarAvail === "boolean") {
        setDocSidecar(
          sidecarAvail
            ? { color: "green", title: "sidecar 通", detail: st?.sidecar?.url }
            : { color: "yellow", title: "sidecar 降级模式", detail: "本地无 sidecar，能力受限" },
        );
      } else {
        setDocSidecar({
          color: "yellow",
          title: "sidecar 降级模式",
          detail: "agentd 未响应，无法检测 sidecar",
        });
      }
    };
    void refresh();
    const id = window.setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  // 2. LLM Key — derived from providers
  useEffect(() => {
    const hasKey = providers.some((p) => Boolean(p.apiKey?.trim()));
    setDocLlmKey(
      hasKey
        ? { color: "green", title: "LLM Key 已配置" }
        : {
            color: "yellow",
            title: "LLM Key 未配置",
            detail: "请在 Onboarding 或 Models 中填写 API Key",
          },
    );
  }, [providers]);

  // 4. workspace — derived from projectPath prop
  useEffect(() => {
    const pp = (projectPath || "").trim();
    setDocWorkspace(
      pp
        ? { color: "green", title: "workspace 已绑定", detail: pp }
        : { color: "yellow", title: "workspace 未绑定", detail: "请在 Onboarding 中选择文件夹" },
    );
  }, [projectPath]);

  useEffect(() => {
    const p = ensureLocalProvider(providers);
    setApiKey(p.apiKey || config.api_key || LOCAL_LLM.apiKey);
    setModel(p.models.find((m) => m.enabled)?.id || p.models[0]?.id || config.model || LOCAL_LLM.model);
    setBaseUrl(p.baseUrl || LOCAL_LLM.baseUrl);
  }, [providers, config.api_key, config.model]);

  const refreshMcp = useCallback(async () => {
    setMcpBusy(true);
    setMcpError(null);
    try {
      const res = await listMcpTrust();
      if (!res.ok) {
        setMcpError(res.error || "加载 MCP 授权列表失败");
        setMcpServers([]);
        return;
      }
      setMcpServers(res.servers);
    } finally {
      setMcpBusy(false);
    }
  }, []);

  useEffect(() => {
    if (section === "mcp") void refreshMcp();
  }, [section, refreshMcp]);

  // ---- Memory ----
  const refreshMemory = useCallback(async () => {
    setMemBusy(true);
    setMemError(null);
    try {
      const stats = await fetchMemoryStats();
      setMemStats(stats);
    } finally {
      setMemBusy(false);
    }
  }, []);

  useEffect(() => {
    if (section === "memory") void refreshMemory();
  }, [section, refreshMemory]);

  const handleMemSearch = async () => {
    if (!memQuery.trim() || !memUserId.trim()) return;
    setMemBusy(true);
    setMemError(null);
    try {
      const res = await fetchMemorySearch({ user_id: memUserId.trim(), query: memQuery.trim(), top_k: 10 });
      if (!res.ok) {
        setMemError(res.error || "搜索失败");
        setMemItems([]);
      } else {
        setMemItems(res.items);
      }
    } finally {
      setMemBusy(false);
    }
  };

  const handleMemCleanup = async () => {
    setMemBusy(true);
    setMemError(null);
    try {
      const res = await cleanupMemory();
      if (!res.ok) {
        setMemError(res.error || "清理失败");
      } else {
        setToast(`清理 ${res.removed ?? 0} 条`);
        await refreshMemory();
      }
    } finally {
      setMemBusy(false);
    }
  };

  // ---- Skills ----
  const refreshSkills = useCallback(async () => {
    setSkillBusy(true);
    setSkillError(null);
    try {
      const list = await fetchSkillsList(
        skillFilter === "all" ? undefined : { status: skillFilter },
      );
      setSkillEntries(list?.entries ?? []);
    } catch (e) {
      setSkillError(String(e));
    } finally {
      setSkillBusy(false);
    }
  }, [skillFilter]);

  useEffect(() => {
    if (section === "skills") void refreshSkills();
  }, [section, refreshSkills]);

  const handleCreateDraft = async () => {
    const name = skillNewName.trim();
    if (!name) {
      setSkillError("技能名不能为空");
      return;
    }
    setSkillBusy(true);
    setSkillError(null);
    try {
      const res = await createSkillDraft({
        name,
        display_name: name,
        description: skillNewDesc.trim(),
        owner_id: "desktop",
        initial_version: "1.0.0",
      });
      if (!res.ok || !res.entry) {
        setSkillError(res.error || "创建失败");
      } else {
        setSkillNewName("");
        setSkillNewDesc("");
        setToast(`草稿已创建: ${res.entry.name}`);
        await refreshSkills();
      }
    } finally {
      setSkillBusy(false);
    }
  };

  const handleSkillAction = async (entry: FnixSkillEntry, action: "submit" | "approve" | "deprecate") => {
    setSkillBusy(true);
    setSkillError(null);
    try {
      let res: { ok: boolean; error?: string };
      if (action === "submit") res = await submitSkillForReview(entry.id);
      else if (action === "approve") res = await approveSkill(entry.id);
      else res = await deprecateSkill(entry.id);
      if (!res.ok) {
        setSkillError(res.error || `${action} failed`);
      } else {
        setToast(`${action} → ${entry.name}`);
        await refreshSkills();
      }
    } finally {
      setSkillBusy(false);
    }
  };

  const buildProvider = (): AIProviderConfig => ({
    id: seed.id || "local-dashscope",
    type: "openai-compatible",
    name: LOCAL_LLM.providerName,
    apiKey: apiKey.trim(),
    baseUrl: baseUrl.trim() || LOCAL_LLM.baseUrl,
    models: [{ id: model.trim() || LOCAL_LLM.model, name: model.trim() || LOCAL_LLM.model, enabled: true }],
  });

  const handleSave = async () => {
    setSaving(true);
    setToast(null);
    try {
      const provider = buildProvider();
      const list = [provider];
      await saveAIProviders(list);
      onProvidersChange(list);
      const nextConfig: AppConfig = {
        ...config,
        provider: LOCAL_LLM.provider,
        model: provider.models[0].id,
        api_key: provider.apiKey,
      };
      await saveConfigToStore(nextConfig);
      onConfigChange(nextConfig);
      await syncHarnessConfig({
        provider: LOCAL_LLM.provider,
        model: nextConfig.model,
        base_url: provider.baseUrl,
        api_key: provider.apiKey,
      });
      setToast("Saved");
    } catch (e) {
      setToast(String(e));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestOk(null);
    try {
      const provider = buildProvider();
      const modelId = provider.models.find((m) => m.enabled)?.id || provider.models[0]?.id || model;
      const harness = await testHarnessLlm({
        provider: LOCAL_LLM.provider,
        model: modelId,
        base_url: provider.baseUrl,
        api_key: provider.apiKey,
      });
      if (harness.ok) {
        setTestOk(true);
        setToast("连接成功");
        return;
      }
      // Fallback: direct provider call (may hit CORS in browser)
      const res = await testConnection(provider, modelId);
      setTestOk(res.success);
      setToast(res.success ? "连接成功" : res.error || harness.error || "连接失败");
    } catch (e) {
      setTestOk(false);
      setToast(String(e));
    } finally {
      setTesting(false);
    }
  };

  const handleApproveMcp = async (row: McpTrustServerRow) => {
    setMcpBusy(true);
    setToast(null);
    const res = await approveMcpTrust({
      server_id: row.name,
      command: row.command || undefined,
      args: row.args?.length ? row.args : undefined,
      remote_url: row.url || undefined,
      notes: "从设置中批准",
    });
    setMcpBusy(false);
    if (!res.ok) {
      setToast(res.error || "批准失败");
      setTestOk(false);
      return;
    }
    setToast(`已批准 ${row.name}`);
    setTestOk(true);
    await refreshMcp();
  };

  const handleDenyMcp = async (row: McpTrustServerRow) => {
    setMcpBusy(true);
    setToast(null);
    const res = await denyMcpTrust({
      server_id: row.name,
      notes: "从设置中拒绝",
    });
    setMcpBusy(false);
    if (!res.ok) {
      setToast(res.error || "拒绝失败");
      setTestOk(false);
      return;
    }
    setToast(`已拒绝 ${row.name}`);
    setTestOk(true);
    await refreshMcp();
  };

  return (
    <div className="fnix-set-root" role="dialog" aria-label="Settings">
      <header className="fnix-set-head">
        <button type="button" className="fnix-set-back" onClick={onClose}>
          <ArrowLeft size={18} />
          Back
        </button>
        <h1>Settings</h1>
        <div className="fnix-set-head-r">
          {toast && <span className={`fnix-set-toast${testOk === false ? " bad" : ""}`}>{toast}</span>}
          <button type="button" className="fnix-set-save" disabled={saving} onClick={() => void handleSave()}>
            {saving ? <Loader2 size={14} className="spin" /> : null}
            Save
          </button>
        </div>
      </header>

      <div className="fnix-set-body">
        <nav className="fnix-set-nav">
          {(
            [
              ["models", "Models"],
              ["mcp", "MCP"],
              ["skills", "Skills"],
              ["memory", "Memory"],
              ["diagnostics", "Diagnostics"],
              ["general", "General"],
              ["about", "About"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`fnix-set-nav-item${section === id ? " on" : ""}`}
              onClick={() => setSection(id)}
            >
              {label}
            </button>
          ))}
        </nav>

        <main className="fnix-set-main">
          {section === "models" && (
            <>
              <div className="fnix-set-title">
                <h2>Models</h2>
                <p>Your local DashScope key. Keys stay on this machine.</p>
              </div>

              <div className="fnix-prov-detail">
                <div className="fnix-field">
                  <label>Provider</label>
                  <div className="fnix-info-card" style={{ marginBottom: 0 }}>
                    <b>{LOCAL_LLM.providerName}</b>
                    <span>{baseUrl || LOCAL_LLM.baseUrl}</span>
                  </div>
                </div>

                <div className="fnix-field">
                  <label>API Key</label>
                  <div className="fnix-key-row">
                    <span className="fnix-key-ico">
                      <KeyRound size={15} />
                    </span>
                    <input
                      type={showKey ? "text" : "password"}
                      value={apiKey}
                      placeholder="sk-…"
                      onChange={(e) => setApiKey(e.target.value)}
                    />
                    <button type="button" className="fnix-ibtn sm" onClick={() => setShowKey((v) => !v)}>
                      {showKey ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>

                <div className="fnix-field">
                  <label>Model</label>
                  <input
                    value={model}
                    placeholder={LOCAL_LLM.model}
                    onChange={(e) => setModel(e.target.value)}
                  />
                </div>

                <details className="fnix-advanced">
                  <summary>Advanced</summary>
                  <div className="fnix-field">
                    <label>Base URL</label>
                    <input
                      value={baseUrl}
                      placeholder={LOCAL_LLM.baseUrl}
                      onChange={(e) => setBaseUrl(e.target.value)}
                    />
                  </div>
                </details>

                <div className="fnix-set-actions">
                  <button
                    type="button"
                    className="fnix-set-save ghost"
                    disabled={testing}
                    onClick={() => void handleTest()}
                  >
                    {testing ? <Loader2 size={14} className="spin" /> : null}
                    Test connection
                  </button>
                  <button
                    type="button"
                    className="fnix-set-save"
                    disabled={saving}
                    onClick={() => void handleSave()}
                  >
                    Save
                  </button>
                </div>
              </div>
            </>
          )}

          {section === "mcp" && (
            <div className="fnix-set-title">
              <h2>MCP Trust</h2>
              <p>
                Servers in <code>~/.fnix/mcp.json</code> stay blocked until you approve them. Trust is
                local-only (fail-closed).
              </p>
              <div className="fnix-set-actions" style={{ marginTop: 12 }}>
                <button
                  type="button"
                  className="fnix-set-save ghost"
                  disabled={mcpBusy}
                  onClick={() => void refreshMcp()}
                >
                  {mcpBusy ? <Loader2 size={14} className="spin" /> : null}
                  Refresh
                </button>
              </div>
              {mcpError ? (
                <div className="fnix-info-card" style={{ marginTop: 12 }}>
                  <b>Could not load trust ledger</b>
                  <span>{mcpError}</span>
                </div>
              ) : null}
              {mcpServers.length === 0 && !mcpError ? (
                <div className="fnix-info-card" style={{ marginTop: 12 }}>
                  <b>No MCP servers configured</b>
                  <span>Add entries to ~/.fnix/mcp.json, then Approve here before connect.</span>
                </div>
              ) : (
                <div style={{ marginTop: 8 }}>
                  {mcpServers.map((row) => (
                    <div key={row.name} className="fnix-mcp-row">
                      <div className="fnix-mcp-meta">
                        <b>{row.name}</b>
                        <span>
                          {row.command
                            ? [row.command, ...(row.args || [])].join(" ")
                            : row.url || "—"}
                        </span>
                        <span className={`fnix-mcp-badge ${row.trust_status}`}>
                          {row.trust_status}
                        </span>
                      </div>
                      <div className="fnix-mcp-actions">
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={mcpBusy || row.trust_status === "approved"}
                          onClick={() => void handleApproveMcp(row)}
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="fnix-set-save ghost"
                          disabled={mcpBusy || row.trust_status === "denied"}
                          onClick={() => void handleDenyMcp(row)}
                        >
                          Deny
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {section === "memory" && (
            <div className="fnix-set-title">
              <h2>Memory</h2>
              <p>三层记忆：短期对话窗口 · 长期向量记忆 · 实体画像。数据存本地，进程内内存版（重启清空）。</p>
              <div className="fnix-info-card" style={{ marginTop: 12 }}>
                <b>统计</b>
                <span>
                  short_term: {memStats?.short_term_count ?? "—"} 条 / {memStats?.short_term_tokens ?? 0} tokens
                  {" · "}long_term: {memStats?.long_term_count ?? "—"} 条
                  {" · "}entity: {memStats?.entity_count ?? "—"} 个
                </span>
                {memStats?.entity_types && Object.keys(memStats.entity_types).length > 0 ? (
                  <span>类型分布: {Object.entries(memStats.entity_types).map(([k, v]) => `${k}=${v}`).join(" · ")}</span>
                ) : null}
              </div>

              <div className="fnix-field" style={{ marginTop: 16 }}>
                <label>长期记忆检索</label>
                <div className="fnix-key-row">
                  <input
                    value={memUserId}
                    placeholder="user_id"
                    onChange={(e) => setMemUserId(e.target.value)}
                    style={{ maxWidth: 140 }}
                  />
                  <input
                    value={memQuery}
                    placeholder="检索查询…"
                    onChange={(e) => setMemQuery(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") void handleMemSearch(); }}
                  />
                  <button
                    type="button"
                    className="fnix-set-save ghost"
                    disabled={memBusy}
                    onClick={() => void handleMemSearch()}
                  >
                    {memBusy ? <Loader2 size={14} className="spin" /> : null}
                    Search
                  </button>
                </div>
                {memError ? <p className="fnix-field-hint" style={{ color: "#c0392b" }}>{memError}</p> : null}
              </div>

              {memItems.length > 0 ? (
                <div style={{ marginTop: 8 }}>
                  {memItems.map((it, i) => (
                    <div key={it.id || i} className="fnix-mcp-row">
                      <div className="fnix-mcp-meta">
                        <b>{(it.content || "").slice(0, 80)}</b>
                        <span>score: {(it.score ?? 0).toFixed(3)} · {it.created_at || ""}</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}

              <div className="fnix-set-actions" style={{ marginTop: 16 }}>
                <button
                  type="button"
                  className="fnix-set-save ghost"
                  disabled={memBusy}
                  onClick={() => void refreshMemory()}
                >
                  {memBusy ? <Loader2 size={14} className="spin" /> : null}
                  Refresh stats
                </button>
                <button
                  type="button"
                  className="fnix-set-save"
                  disabled={memBusy}
                  onClick={() => void handleMemCleanup()}
                >
                  Cleanup expired
                </button>
              </div>
            </div>
          )}

          {section === "skills" && (
            <div className="fnix-set-title">
              <h2>Skills</h2>
              <p>技能市场生命周期：DRAFT → PENDING_REVIEW → PUBLISHED → DEPRECATED。STP 调度运行时权重，这里管生命周期。</p>

              <div className="fnix-field" style={{ marginTop: 12 }}>
                <label>新建草稿</label>
                <div className="fnix-key-row">
                  <input
                    value={skillNewName}
                    placeholder="skill-name (a-z 0-9 _ -)"
                    onChange={(e) => setSkillNewName(e.target.value)}
                  />
                  <input
                    value={skillNewDesc}
                    placeholder="描述（可选）"
                    onChange={(e) => setSkillNewDesc(e.target.value)}
                  />
                  <button
                    type="button"
                    className="fnix-set-save"
                    disabled={skillBusy}
                    onClick={() => void handleCreateDraft()}
                  >
                    {skillBusy ? <Loader2 size={14} className="spin" /> : null}
                    Create draft
                  </button>
                </div>
              </div>

              <div className="fnix-field" style={{ marginTop: 12 }}>
                <label>状态过滤</label>
                <select
                  value={skillFilter}
                  onChange={(e) => setSkillFilter(e.target.value as FnixSkillStatus | "all")}
                >
                  <option value="all">All</option>
                  <option value="draft">draft</option>
                  <option value="pending_review">pending_review</option>
                  <option value="published">published</option>
                  <option value="rejected">rejected</option>
                  <option value="deprecated">deprecated</option>
                </select>
              </div>

              {skillError ? (
                <div className="fnix-info-card" style={{ marginTop: 12 }}>
                  <b>Error</b>
                  <span>{skillError}</span>
                </div>
              ) : null}

              {skillEntries.length === 0 && !skillError ? (
                <div className="fnix-info-card" style={{ marginTop: 12 }}>
                  <b>无技能</b>
                  <span>新建一个草稿开始流程。</span>
                </div>
              ) : (
                <div style={{ marginTop: 8 }}>
                  {skillEntries.map((entry) => (
                    <div key={entry.id} className="fnix-mcp-row">
                      <div className="fnix-mcp-meta">
                        <b>{entry.display_name || entry.name}</b>
                        <span>
                          {entry.name} · v{entry.latest_version || "—"} · {entry.category}
                        </span>
                        <span className={`fnix-mcp-badge ${entry.status}`}>
                          {entry.status}
                        </span>
                        {entry.description ? <span>{entry.description}</span> : null}
                      </div>
                      <div className="fnix-mcp-actions">
                        {entry.status === "draft" ? (
                          <button
                            type="button"
                            className="fnix-set-save"
                            disabled={skillBusy}
                            onClick={() => void handleSkillAction(entry, "submit")}
                          >
                            Submit
                          </button>
                        ) : null}
                        {entry.status === "pending_review" ? (
                          <button
                            type="button"
                            className="fnix-set-save"
                            disabled={skillBusy}
                            onClick={() => void handleSkillAction(entry, "approve")}
                          >
                            Approve
                          </button>
                        ) : null}
                        {entry.status === "published" ? (
                          <button
                            type="button"
                            className="fnix-set-save ghost"
                            disabled={skillBusy}
                            onClick={() => void handleSkillAction(entry, "deprecate")}
                          >
                            Deprecate
                          </button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="fnix-set-actions" style={{ marginTop: 16 }}>
                <button
                  type="button"
                  className="fnix-set-save ghost"
                  disabled={skillBusy}
                  onClick={() => void refreshSkills()}
                >
                  {skillBusy ? <Loader2 size={14} className="spin" /> : null}
                  Refresh
                </button>
              </div>
            </div>
          )}

          {section === "diagnostics" && (
            <div className="fnix-set-title">
              <h2>Diagnostics</h2>
              <p>五项红黄绿状态卡：agentd · LLM Key · ~/.fnix · workspace · sidecar。每 30 秒自动刷新。</p>
              {(() => {
                const cards = [docAgentd, docLlmKey, docHome, docWorkspace, docSidecar].filter(
                  (c): c is { color: "green" | "yellow" | "red"; title: string; detail?: string } =>
                    c !== null && c.color !== "green",
                );
                const needAttention = cards.length;
                return (
                  <div className={`doc-summary${needAttention > 0 ? " warn" : ""}`}>
                    {needAttention === 0 ? "全部就绪" : `${needAttention} 项需关注`}
                  </div>
                );
              })()}
              <div className="doc-grid">
                {([
                  ["agentd", docAgentd],
                  ["LLM Key", docLlmKey],
                  ["~/.fnix", docHome],
                  ["workspace", docWorkspace],
                  ["sidecar", docSidecar],
                ] as const).map(([key, card]) => (
                  <div
                    key={key}
                    className={`doc-card doc-card-${card?.color ?? "yellow"}`}
                  >
                    <div className="doc-card-head">
                      <span className="doc-card-name">{key}</span>
                      <span className="doc-card-status">{card?.title ?? "检测中…"}</span>
                    </div>
                    {card?.detail ? <div className="doc-card-detail">{card.detail}</div> : null}
                    {key === "LLM Key" && card?.color === "yellow" ? (
                      <button
                        type="button"
                        className="doc-card-cta"
                        onClick={onClose}
                      >
                        去 Onboarding 配置
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
              <div className="fnix-set-actions" style={{ marginTop: 16 }}>
                <button
                  type="button"
                  className="fnix-set-save"
                  disabled={doctorBusy}
                  onClick={() => {
                    setDoctorBusy(true);
                    void runRuntimeDoctor()
                      .then(setDoctor)
                      .finally(() => setDoctorBusy(false));
                  }}
                >
                  {doctorBusy ? "检查中…" : "运行运行时诊断"}
                </button>
                <button type="button" className="fnix-set-save" onClick={() => onOpenBenchmark?.()}>
                  打开全链路测试面板
                </button>
              </div>
              {doctor && (
                <div className="fnix-info-card" style={{ marginTop: 16 }}>
                  <b>{doctor.ok ? "运行时正常" : "运行时需要检查"}</b>
                  <span>
                    API {doctor.apiBase || "—"} · sidecar {doctor.sidecarUrl || "—"}
                  </span>
                  <span>
                    agentd binary {doctor.agentdBinary ? "yes" : "no"} · Keychain{" "}
                    {doctor.keychainOk ? "ok" : "unavailable"} · {doctor.os}/{doctor.arch}
                  </span>
                  {doctor.notes?.length ? (
                    <span>{doctor.notes.join(" · ")}</span>
                  ) : null}
                </div>
              )}
              <div className="fnix-info-card" style={{ marginTop: 12 }}>
                <b>Composer 快捷指令</b>
                <span>
                  <code>/benchmark</code> · <code>全链路测试</code>
                </span>
              </div>
            </div>
          )}

          {section === "general" && (
            <div className="fnix-set-title">
              <h2>General</h2>
              <p>Fnix keeps chats and keys local. No account login required.</p>
              <div className="fnix-field" style={{ marginTop: 16 }}>
                <label htmlFor="fnix-theme">Appearance</label>
                <select
                  id="fnix-theme"
                  value={normalizeThemePref(config.theme)}
                  onChange={(e) => {
                    const theme = e.target.value as "light" | "dark" | "system";
                    onConfigChange({ ...config, theme });
                    void saveConfigToStore({ ...config, theme });
                  }}
                >
                  <option value="system">System</option>
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </select>
                <p className="fnix-field-hint">
                  High contrast and reduced motion follow OS accessibility settings.
                </p>
              </div>
              <div className="fnix-info-card">
                <b>当前模型</b>
                <span>{model || LOCAL_LLM.model}</span>
              </div>
            </div>
          )}

          {section === "about" && (
            <div className="fnix-set-title">
              <h2>About</h2>
              <p>Fnix Desktop — Desktop-look shell on React + Tauri 2.</p>
              <div className="fnix-info-card">
                <b>Local LLM</b>
                <span>
                  {LOCAL_LLM.providerName} · {model || LOCAL_LLM.model}
                </span>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
