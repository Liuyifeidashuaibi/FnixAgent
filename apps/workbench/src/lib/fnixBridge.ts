/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * FnixAgent bridge — sync Workbench BYOK / workspace with agentd (~/.fnix).
 * UI remains Tauri-native; agentd is the Python brain for Work / harness APIs.
 */

import { invoke } from "@tauri-apps/api/core";

/** 端口单一来源：vite proxy → FNIX_AGENTD_URL (默认 127.0.0.1:8003) */
const DEFAULT_API = "http://127.0.0.1:8003";
const env = (import.meta as ImportMeta & { env?: Record<string, string> }).env;
// In browser dev (vite), use a relative base so requests flow through the
// vite proxy (avoids direct CORS preflight to 127.0.0.1:8003). Tauri runtime
// will overwrite this via runtime_bootstrap with an absolute URL.
const isDev = Boolean(env?.DEV);
let runtimeApiBase = (
  isDev
    ? (env?.VITE_API_BASE_DEV || "") // "" → relative, goes through vite proxy
    : (env?.FNIX_AGENTD_URL || env?.VITE_API_BASE || env?.API_TARGET || DEFAULT_API)
).replace(/\/$/, "");
let runtimeCapabilityToken = (env?.VITE_FNIX_CAPABILITY_TOKEN || "").trim();

export interface FnixRuntimeConfig {
  apiBase: string;
  sidecarUrl: string;
  capabilityToken?: string;
  packaged: boolean;
}

export interface FnixRuntimeDoctorReport {
  ok: boolean;
  apiBase: string;
  sidecarUrl: string;
  packaged: boolean;
  capabilityConfigured: boolean;
  agentdBinary: boolean;
  sidecarBinary: boolean;
  pythonFallback: boolean;
  agentdHealthy: boolean;
  sidecarHealthy: boolean;
  keychainOk: boolean;
  agentdRestarts: number;
  sidecarRestarts: number;
  arch: string;
  os: string;
  notes: string[];
}

/**
 * Resolve the managed Tauri runtime before rendering the product shell.
 * Browser development keeps using the Vite/env fallback.
 */
export async function initializeFnixRuntime(): Promise<FnixRuntimeConfig | null> {
  try {
    const config = await invoke<FnixRuntimeConfig>("runtime_bootstrap");
    if (config.apiBase?.trim()) {
      runtimeApiBase = config.apiBase.trim().replace(/\/$/, "");
    }
    if (config.capabilityToken?.trim()) {
      runtimeCapabilityToken = config.capabilityToken.trim();
    }
    return config;
  } catch {
    return null;
  }
}

export function getFnixApiBase(): string {
  return runtimeApiBase;
}

export function getFnixCapabilityToken(): string {
  return runtimeCapabilityToken;
}

export function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...(extra || {}) };
  if (runtimeCapabilityToken) {
    headers["X-Fnix-Capability"] = runtimeCapabilityToken;
  }
  return headers;
}

async function fnixFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = new Headers(init?.headers || undefined);
  const auth = authHeaders();
  for (const [key, value] of Object.entries(auth)) {
    headers.set(key, value);
  }
  return fetch(`${getFnixApiBase()}${path}`, {
    ...init,
    headers,
  });
}

/** Test LLM via agentd harness (preferred over browser→vendor CORS). */
export async function testHarnessLlm(input: {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key: string;
}): Promise<{ ok: boolean; error?: string; preview?: string }> {
  try {
    const res = await fnixFetch("/api/v1/harness/llm/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: input.provider,
        model: input.model,
        base_url: input.base_url,
        api_key: input.api_key.trim(),
      }),
      signal: AbortSignal.timeout(20000),
    });
    const data = (await res.json().catch(() => ({}))) as {
      ok?: boolean;
      detail?: string;
      preview?: string;
    };
    if (!res.ok) {
      return { ok: false, error: data.detail || `HTTP ${res.status}` };
    }
    return { ok: Boolean(data.ok ?? true), preview: data.preview };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

export interface FnixHarnessConfig {
  provider?: string;
  model?: string;
  base_url?: string;
  has_api_key?: boolean;
  key_hint?: string;
}

/** Push harness config into ~/.fnix (provider/model → config.toml; api_key → secrets.json).
 *  Desktop 同时写 OS Keychain（saveConfigToStore）与 secrets.json，确保 CLI（fnixagent chat）
 *  与 Python LLMAdapter._auto_detect() 能读到同一份 Key，消除双存储割裂。 */
export async function syncHarnessConfig(input: {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
}): Promise<boolean> {
  try {
    const res = await fnixFetch("/api/v1/harness/config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider: input.provider,
        model: input.model,
        base_url: input.base_url,
        // 同步写入 ~/.fnix/secrets.json，供 CLI 与后端自动检测复用（本机存储，与 .env 同级风险）。
        api_key: input.api_key,
      }),
      signal: AbortSignal.timeout(4000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Pull harness summary (no raw key). */
export async function loadHarnessConfig(): Promise<FnixHarnessConfig | null> {
  try {
    const res = await fnixFetch("/api/v1/harness/config", {
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    return (await res.json()) as FnixHarnessConfig;
  } catch {
    return null;
  }
}

/** Harness status snapshot — home dir, sidecar availability, setup flags. */
export interface FnixHarnessStatus {
  home_dir?: { exists?: boolean; path?: string };
  sidecar?: { available?: boolean; url?: string; version?: string; runtime?: string };
  setup?: { has_provider?: boolean; has_model?: boolean; has_api_key?: boolean };
}

/** Fetch harness status (used by Diagnostics cards). */
export async function fetchHarnessStatus(): Promise<FnixHarnessStatus | null> {
  try {
    const res = await fnixFetch("/api/v1/harness/status", {
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    return (await res.json().catch(() => null)) as FnixHarnessStatus | null;
  } catch {
    return null;
  }
}

/** Localhost-only BYOK bootstrap from agentd process env (repo .env). */
export async function loadLocalLlmBootstrap(): Promise<{
  provider: string;
  model: string;
  base_url: string;
  api_key: string;
  provider_name?: string;
} | null> {
  try {
    const res = await fnixFetch("/api/v1/harness/local-bootstrap", {
      signal: AbortSignal.timeout(2500),
    });
    if (!res.ok) return null;
    const data = (await res.json()) as {
      ok?: boolean;
      provider?: string;
      model?: string;
      base_url?: string;
      api_key?: string;
      provider_name?: string;
    };
    if (!data.api_key?.trim()) return null;
    return {
      provider: data.provider || "qwen",
      model: data.model || "qwen-plus-2025-07-28",
      base_url: data.base_url || "",
      api_key: data.api_key.trim(),
      provider_name: data.provider_name,
    };
  } catch {
    return null;
  }
}

/** Ensure `{workspace}/.fnix` layout exists on disk via agentd. */
export async function ensureFnixWorkspace(workspace: string): Promise<boolean> {
  const path = (workspace || "").trim();
  if (!path) return false;
  try {
    const res = await fnixFetch("/api/v1/harness/workspace/ensure", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: path }),
      signal: AbortSignal.timeout(8000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

export async function pingAgentd(opts?: { timeoutMs?: number }): Promise<boolean> {
  try {
    // /health stays public even when capability is required.
    const res = await fetch(`${getFnixApiBase()}/health`, {
      signal: AbortSignal.timeout(opts?.timeoutMs ?? 4000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Desktop Doctor — runtime ports, binaries, Keychain, restart budget. */
export async function runRuntimeDoctor(): Promise<FnixRuntimeDoctorReport | null> {
  try {
    return await invoke<FnixRuntimeDoctorReport>("runtime_doctor");
  } catch {
    return null;
  }
}

export type McpTrustServerRow = {
  name: string;
  enabled: boolean;
  command: string;
  args: string[];
  url: string;
  trust_status: string;
  command_hash: string;
  notes: string;
};

/** List MCP servers from ~/.fnix/mcp.json with trust ledger status. */
export async function listMcpTrust(): Promise<{
  ok: boolean;
  servers: McpTrustServerRow[];
  error?: string;
}> {
  try {
    const res = await fnixFetch("/api/v1/harness/mcp/trust", {
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) {
      return { ok: false, servers: [], error: await res.text().catch(() => res.statusText) };
    }
    const data = (await res.json()) as { ok?: boolean; servers?: McpTrustServerRow[] };
    return { ok: Boolean(data.ok), servers: data.servers || [] };
  } catch (e) {
    return { ok: false, servers: [], error: String(e) };
  }
}

/** Approve MCP server in fail-closed trust ledger, then reload registry. */
export async function approveMcpTrust(input: {
  server_id: string;
  command?: string;
  args?: string[];
  remote_url?: string;
  notes?: string;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch("/api/v1/harness/mcp/trust/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** Deny MCP server in trust ledger. */
export async function denyMcpTrust(input: {
  server_id: string;
  notes?: string;
}): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch("/api/v1/harness/mcp/trust/deny", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(8000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ─── MCP config (add / edit servers in ~/.fnix/mcp.json) ──────────────────

export interface McpServerConfig {
  name: string;
  enabled?: boolean;
  command?: string;
  args?: string[];
  url?: string;
  env?: Record<string, string>;
}

/** Read the raw ~/.fnix/mcp.json server list. */
export async function fetchMcpConfig(): Promise<{
  ok: boolean;
  version?: number;
  servers?: McpServerConfig[];
  error?: string;
}> {
  try {
    const res = await fnixFetch("/api/v1/harness/mcp", {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    const data = (await res.json()) as { ok?: boolean; version?: number; servers?: McpServerConfig[] };
    return { ok: Boolean(data.ok ?? true), version: data.version, servers: data.servers || [] };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** Write ~/.fnix/mcp.json (add/update servers) and hot-reload the registry. */
export async function updateMcpConfig(input: {
  version: number;
  servers: McpServerConfig[];
}): Promise<{ ok: boolean; loaded?: number; error?: string }> {
  try {
    const res = await fnixFetch("/api/v1/harness/mcp", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    const data = (await res.json().catch(() => ({}))) as { ok?: boolean; loaded?: number };
    return { ok: Boolean(data.ok ?? true), loaded: data.loaded };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ===========================================================================
// Memory 三层记忆（S1.2.4）
// ===========================================================================

export interface FnixMemoryStats {
  short_term_count?: number;
  short_term_tokens?: number;
  long_term_count?: number;
  entity_count?: number;
  entity_types?: Record<string, number>;
}

export interface FnixMemoryItem {
  id?: string;
  content?: string;
  user_id?: string;
  score?: number;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

/** 三层记忆统计（short/long/entity 计数）。 */
export async function fetchMemoryStats(): Promise<FnixMemoryStats | null> {
  try {
    const res = await fnixFetch("/api/v1/memory/stats", {
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    return (await res.json()) as FnixMemoryStats;
  } catch {
    return null;
  }
}

/** 长期记忆语义检索。 */
export async function fetchMemorySearch(input: {
  user_id: string;
  query: string;
  top_k?: number;
}): Promise<{ ok: boolean; items: FnixMemoryItem[]; count?: number; error?: string }> {
  try {
    const params = new URLSearchParams({
      user_id: input.user_id,
      query: input.query,
    });
    if (input.top_k) params.set("top_k", String(input.top_k));
    const res = await fnixFetch(`/api/v1/memory/long_term?${params.toString()}`, {
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, items: [], error: await res.text().catch(() => res.statusText) };
    }
    const data = (await res.json()) as { count?: number; items?: FnixMemoryItem[] };
    return { ok: true, items: data.items || [], count: data.count };
  } catch (e) {
    return { ok: false, items: [], error: String(e) };
  }
}

/** 清理过期长期记忆。 */
export async function cleanupMemory(): Promise<{ ok: boolean; removed?: number; error?: string }> {
  try {
    const res = await fnixFetch("/api/v1/memory/cleanup", {
      method: "POST",
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    const data = (await res.json()) as { ok?: boolean; removed?: number };
    return { ok: Boolean(data.ok), removed: data.removed };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ===========================================================================
// Skills 技能市场（S1.2.3）
// ===========================================================================

export type FnixSkillStatus = "draft" | "pending_review" | "published" | "rejected" | "deprecated";

export interface FnixSkillEntry {
  id: string;
  name: string;
  display_name: string;
  description: string;
  category: string;
  tags: string[];
  owner_id: string;
  status: FnixSkillStatus;
  latest_version: string | null;
  install_count: number;
  rating: number;
  rating_count: number;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  reviewer_id: string;
  review_comment: string;
}

export interface FnixSkillsList {
  entries: FnixSkillEntry[];
  count: number;
  stats: {
    total: number;
    by_status: Record<string, number>;
    published: number;
    total_installs: number;
  };
}

/** 列出技能条目（支持 status 过滤）。 */
export async function fetchSkillsList(input?: {
  status?: FnixSkillStatus;
  category?: string;
}): Promise<FnixSkillsList | null> {
  try {
    const params = new URLSearchParams();
    if (input?.status) params.set("status", input.status);
    if (input?.category) params.set("category", input.category);
    const qs = params.toString();
    const res = await fnixFetch(`/api/v1/skills${qs ? `?${qs}` : ""}`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return (await res.json()) as FnixSkillsList;
  } catch {
    return null;
  }
}

/** 列出 DRAFT 态技能。 */
export async function fetchSkillDrafts(): Promise<{ drafts: FnixSkillEntry[]; count: number } | null> {
  try {
    const res = await fnixFetch("/api/v1/skills/drafts", {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return (await res.json()) as { drafts: FnixSkillEntry[]; count: number };
  } catch {
    return null;
  }
}

/** 创建技能草稿。 */
export async function createSkillDraft(input: {
  name: string;
  display_name?: string;
  description?: string;
  category?: string;
  tags?: string[];
  owner_id?: string;
  initial_version?: string;
  initial_changelog?: string;
}): Promise<{ ok: boolean; entry?: FnixSkillEntry; error?: string }> {
  try {
    const res = await fnixFetch("/api/v1/skills/drafts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(6000),
    });
    const data = (await res.json().catch(() => ({}))) as { ok?: boolean; entry?: FnixSkillEntry; detail?: string };
    if (!res.ok) {
      return { ok: false, error: data.detail || `HTTP ${res.status}` };
    }
    return { ok: Boolean(data.ok ?? true), entry: data.entry };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 提交审核。 */
export async function submitSkillForReview(entryId: string, reviewerId = "desktop"): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/skills/${entryId}/submit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer_id: reviewerId }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 审批通过。 */
export async function approveSkill(entryId: string, reviewerId = "desktop", comment = ""): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/skills/${entryId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewer_id: reviewerId, comment }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 弃用。 */
export async function deprecateSkill(entryId: string, reason = ""): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/skills/${entryId}/deprecate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ comment: reason }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ===========================================================================
// Trae Skill 系统：静态技能 CRUD + 启停（.fnix/skills/*.md）
// 技能管理面板
// ===========================================================================

export interface HarnessSkill {
  name: string;
  path: string;
  preview: string;
  content: string;
  description: string;
  triggers: string[];
  priority: "high" | "normal" | "low";
  enabled: boolean;
}

export interface HarnessSkillsList {
  ok: boolean;
  workspace: string;
  count: number;
  skills: HarnessSkill[];
}

/** 列出 workspace/.fnix/skills 下的所有静态技能。 */
export async function fetchHarnessSkills(workspace: string): Promise<HarnessSkillsList | null> {
  try {
    const qs = new URLSearchParams({ workspace });
    const res = await fnixFetch(`/api/v1/harness/skills?${qs}`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    return (await res.json()) as HarnessSkillsList;
  } catch {
    return null;
  }
}

/** 创建或更新静态技能。 */
export async function writeHarnessSkill(input: {
  workspace: string;
  name: string;
  content: string;
  description?: string;
  triggers?: string[];
  priority?: "high" | "normal" | "low";
  enabled?: boolean;
}): Promise<{ ok: boolean; skill?: HarnessSkill; error?: string }> {
  try {
    const res = await fnixFetch("/api/v1/harness/skills/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(6000),
    });
    const data = (await res.json().catch(() => ({}))) as { ok?: boolean; skill?: HarnessSkill; detail?: string };
    if (!res.ok) {
      return { ok: false, error: data.detail || `HTTP ${res.status}` };
    }
    return { ok: true, skill: data.skill };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 删除静态技能。 */
export async function deleteHarnessSkill(workspace: string, name: string): Promise<{ ok: boolean; error?: string }> {
  try {
    const qs = new URLSearchParams({ workspace });
    const res = await fnixFetch(`/api/v1/harness/skills/${encodeURIComponent(name)}?${qs}`, {
      method: "DELETE",
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 切换静态技能 enabled 状态。 */
export async function toggleHarnessSkill(
  workspace: string,
  name: string,
  enabled: boolean,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/harness/skills/${encodeURIComponent(name)}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace, enabled }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ─── Spec 3: Artifact Canvas 增量编辑 ────────────────────────────────────
// 对标 画布编辑 / 内联编辑 / 搜索替换 block
// 后端端点: POST /api/v1/work/artifacts/write 和 /artifacts/apply

export interface ArtifactWriteResult {
  ok: boolean;
  path?: string;
  size?: number;
  error?: string;
}

export interface ArtifactApplyResult {
  ok: boolean;
  path?: string;
  size?: number;
  applied_blocks?: number;
  results?: Array<{
    applied: boolean;
    error?: string;
    diffRanges?: Array<{ startLine: number; endLine: number }>;
  }>;
  error?: string;
}

/**
 * 整文件写入(用户手动保存)
 */
export async function writeArtifact(input: {
  path: string;
  content: string;
  workspace?: string;
}): Promise<ArtifactWriteResult> {
  try {
    const res = await fnixFetch("/api/v1/work/artifacts/write", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return (await res.json()) as ArtifactWriteResult;
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/**
 * 应用 SEARCH/REPLACE patch(AI 增量编辑)
 *
 * patch 格式:
 *   <<<<<<< SEARCH
 *   原始片段
 *   =======
 *   替换片段
 *   >>>>>>> REPLACE
 */
export async function applyArtifactPatch(input: {
  path: string;
  patch: string;
  workspace?: string;
}): Promise<ArtifactApplyResult> {
  try {
    const res = await fnixFetch("/api/v1/work/artifacts/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(10000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return (await res.json()) as ArtifactApplyResult;
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

// ===========================================================================
// HITL 人机协同审批（Human-in-the-Loop）
// ===========================================================================

/** 待审批的高危工具调用条目。 */
export interface FnixHitlToolApproval {
  idempotency_key: string;
  tool: string;
  risk: string;
  timestamp: string;
}

/** 待审批的流程守门（gate）条目。 */
export interface FnixHitlGate {
  id: string;
  gate: string;
  context: string;
  timestamp: string;
  status: string;
}

/** GET /api/v1/hitl/pending 响应体。 */
export interface FnixHitlPending {
  tool_approvals: FnixHitlToolApproval[];
  gates: FnixHitlGate[];
  /** 已配置自动放行（无需人工确认）的守门名称列表。 */
  auto_approve_gates: string[];
}

/** 构造空的待审批结构（请求失败时兜底，避免 UI 判空）。 */
function emptyHitlPending(): FnixHitlPending {
  return { tool_approvals: [], gates: [], auto_approve_gates: [] };
}

/** 拉取 HITL 待审批队列（高危工具调用 + 流程守门）。 */
export async function listHitlPending(): Promise<{
  ok: boolean;
  pending: FnixHitlPending;
  error?: string;
}> {
  try {
    const res = await fnixFetch("/api/v1/hitl/pending", {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      return {
        ok: false,
        pending: emptyHitlPending(),
        error: await res.text().catch(() => res.statusText),
      };
    }
    const data = (await res.json().catch(() => null)) as Partial<FnixHitlPending> | null;
    return {
      ok: true,
      pending: {
        tool_approvals: data?.tool_approvals || [],
        gates: data?.gates || [],
        auto_approve_gates: data?.auto_approve_gates || [],
      },
    };
  } catch (e) {
    return { ok: false, pending: emptyHitlPending(), error: String(e) };
  }
}

/** 批准待审批的工具调用（按幂等键，可附带反馈）。 */
export async function approveHitlTool(
  key: string,
  feedback = "",
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/hitl/tool/${encodeURIComponent(key)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback }),
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 拒绝待审批的工具调用（可附带理由）。 */
export async function rejectHitlTool(
  key: string,
  reason = "",
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/hitl/tool/${encodeURIComponent(key)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 批准流程守门请求（可附带反馈）。 */
export async function approveHitlGate(
  requestId: string,
  feedback = "",
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/hitl/gate/${encodeURIComponent(requestId)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback }),
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}

/** 拒绝流程守门请求（需给出理由）。 */
export async function rejectHitlGate(
  requestId: string,
  reason = "",
): Promise<{ ok: boolean; error?: string }> {
  try {
    const res = await fnixFetch(`/api/v1/hitl/gate/${encodeURIComponent(requestId)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) {
      return { ok: false, error: await res.text().catch(() => res.statusText) };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
}
