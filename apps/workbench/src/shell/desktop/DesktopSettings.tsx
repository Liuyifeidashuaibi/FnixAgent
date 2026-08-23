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
import {
  ArrowLeft,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  SlidersHorizontal,
  Cpu,
  Boxes,
  Wrench,
  Brain,
  Activity,
  Info,
  CheckCircle2,
  XCircle,
  Sparkles,
  Zap,
  type LucideIcon,
} from "lucide-react";
import type { AppConfig } from "../../utils/tauri";
import { saveAIProviders, saveConfigToStore } from "../../utils/tauri";
import { testConnection, type AIProviderConfig } from "../../utils/providers";
import {
  approveMcpTrust,
  denyMcpTrust,
  loadHarnessConfig,
  fetchHarnessStatus,
  fetchMcpConfig,
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
  updateMcpConfig,
  cleanupMemory,
  type FnixHarnessConfig,
  type FnixRuntimeDoctorReport,
  type FnixMemoryStats,
  type FnixMemoryItem,
  type FnixSkillEntry,
  type FnixSkillStatus,
  type McpServerConfig,
  type McpTrustServerRow,
} from "../../lib/fnixBridge";
import { LOCAL_LLM, localProviderConfig } from "./localLlm";
import {
  FNIX_VERSION,
  FNIX_BUILD_NUMBER,
  FNIX_RELEASE_DATE,
  FNIX_RELEASE_CHANNEL,
  FNIX_LICENSE,
  FNIX_CHANGELOG,
} from "../../config/alpha";
import "./DesktopSettings.css";

type Section = "general" | "models" | "about" | "diagnostics" | "mcp" | "memory" | "skills";

const NAV_GROUPS: { label: string; items: [Section, string][] }[] = [
  { label: "偏好", items: [["general", "General"]] },
  { label: "模型", items: [["models", "Models"]] },
  { label: "连接", items: [["mcp", "MCP"], ["skills", "Skills"]] },
  { label: "数据", items: [["memory", "Memory"]] },
  { label: "系统", items: [["diagnostics", "Diagnostics"], ["about", "About"]] },
];

const SECTION_META: Record<Section, { title: string; desc: string; icon: LucideIcon }> = {
  general: { title: "偏好", desc: "外观与基础设置。", icon: SlidersHorizontal },
  models: { title: "模型", desc: "配置本地 LLM 与 API Key（仅存本机）。", icon: Cpu },
  mcp: { title: "MCP 服务器", desc: "管理模型上下文协议连接（fail-closed 本地授权）。", icon: Boxes },
  skills: { title: "技能", desc: "技能市场生命周期：草稿 → 审核 → 发布。", icon: Wrench },
  memory: { title: "记忆", desc: "三层本地记忆：短期 / 长期 / 实体。", icon: Brain },
  diagnostics: { title: "诊断", desc: "查看 Fnix 当前能否正常工作；如有问题会直接给出处理建议。", icon: Activity },
  about: { title: "关于", desc: "产品能力、版本与许可证。", icon: Info },
};

/** 统一区块标题：品牌图标块 + 标题 + 描述（SECTION_META 驱动，确保 7 个区块视觉一致）。 */
function SectionHeader({ section }: { section: Section }) {
  const meta = SECTION_META[section];
  const Icon = meta.icon;
  return (
    <div className="fnix-set-title-head">
      <span className="fnix-set-title-ico"><Icon size={18} /></span>
      <div>
        <h2>{meta.title}</h2>
        <p>{meta.desc}</p>
      </div>
    </div>
  );
}

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

/** Provider presets — selecting one fills sensible base_url / model defaults. */
const MODEL_PRESETS: { id: string; name: string; baseUrl: string; model: string }[] = [
  { id: "glm", name: "GLM（智谱）", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4.5-flash" },
  { id: "qwen", name: "DashScope（通义千问）", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", model: "qwen-plus-2025-07-28" },
  { id: "deepseek", name: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  { id: "openai", name: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { id: "custom", name: "自定义 / 其他", baseUrl: "", model: "" },
];

/** MCP 样例模板 — 一键导入常见社区 MCP 服务器（导入后需「授权」方可连接，fail-closed）。
 *  FnixAgent 不内置任何 MCP 服务器；这些仅作为可导入的起点样例。*/
const MCP_TEMPLATES: { name: string; desc: string; command: string; args: string[]; url?: string }[] = [
  { name: "filesystem", desc: "读写本地文件系统（建议指定目录）", command: "npx", args: ["-y", "@modelcontextprotocol/server-filesystem", "."] },
  { name: "fetch", desc: "网页抓取与正文提取", command: "uvx", args: ["mcp-server-fetch"] },
  { name: "github", desc: "GitHub 仓库 / Issue / PR（需 Token）", command: "npx", args: ["-y", "@modelcontextprotocol/server-github"] },
  { name: "git", desc: "本地 Git 仓库读写", command: "uvx", args: ["mcp-server-git"] },
  { name: "sqlite", desc: "本地 SQLite 数据库查询", command: "uvx", args: ["mcp-server-sqlite", "--db-path", "./data.db"] },
  { name: "time", desc: "时区与时间转换", command: "uvx", args: ["mcp-server-time"] },
];

/** 提供商头像字（中文优先，便于一眼识别）。 */
const PROVIDER_GLYPH: Record<string, string> = {
  glm: "智",
  qwen: "通",
  deepseek: "深",
  openai: "AI",
  custom: "自",
};

/** 状态 → 中文标签（对标 Trae / WorkBuddy 的本地化状态呈现）。 */
const SKILL_STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  pending_review: "审核中",
  published: "已发布",
  rejected: "已拒绝",
  deprecated: "已弃用",
};
const SKILL_FILTERS: { value: FnixSkillStatus | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "draft", label: "草稿" },
  { value: "pending_review", label: "审核中" },
  { value: "published", label: "已发布" },
  { value: "rejected", label: "已拒绝" },
  { value: "deprecated", label: "已弃用" },
];
const MCP_STATUS_LABEL: Record<string, string> = {
  approved: "已授权",
  denied: "已拒绝",
  pending: "待授权",
};
const MCP_DOT: Record<string, string> = {
  approved: "green",
  denied: "red",
  pending: "yellow",
};

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
}: Props) {
  const [section, setSection] = useState<Section>(initialSection);
  const seed = ensureLocalProvider(providers);
  const [apiKey, setApiKey] = useState(seed.apiKey || config.api_key || LOCAL_LLM.apiKey);
  const [model, setModel] = useState(
    seed.models.find((m) => m.enabled)?.id || seed.models[0]?.id || config.model || LOCAL_LLM.model,
  );
  const [baseUrl, setBaseUrl] = useState(seed.baseUrl || LOCAL_LLM.baseUrl);
  const [showKey, setShowKey] = useState(false);
  const [provider, setProvider] = useState(LOCAL_LLM.provider);
  const [keyHint, setKeyHint] = useState<string | null>(null);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [doctor, setDoctor] = useState<FnixRuntimeDoctorReport | null>(null);
  const [doctorBusy, setDoctorBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);
  const [mcpServers, setMcpServers] = useState<McpTrustServerRow[]>([]);
  const [mcpBusy, setMcpBusy] = useState(false);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [mcpLoaded, setMcpLoaded] = useState(false);
  const [mcpAdding, setMcpAdding] = useState(false);
  const [mcpAddOpen, setMcpAddOpen] = useState(false);
  const [mcpAddName, setMcpAddName] = useState("");
  const [mcpAddCmd, setMcpAddCmd] = useState("");
  const [mcpAddUrl, setMcpAddUrl] = useState("");

  // Memory (S1.2.4)
  const [memStats, setMemStats] = useState<FnixMemoryStats | null>(null);
  const [memQuery, setMemQuery] = useState("");
  const [memUserId, setMemUserId] = useState("desktop");
  const [memItems, setMemItems] = useState<FnixMemoryItem[]>([]);
  const [memBusy, setMemBusy] = useState(false);
  const [memError, setMemError] = useState<string | null>(null);
  const [memLoaded, setMemLoaded] = useState(false);

  // Skills (S1.2.3)
  const [skillEntries, setSkillEntries] = useState<FnixSkillEntry[]>([]);
  const [skillFilter, setSkillFilter] = useState<FnixSkillStatus | "all">("all");
  const [skillBusy, setSkillBusy] = useState(false);
  const [skillError, setSkillError] = useState<string | null>(null);
  const [skillNewName, setSkillNewName] = useState("");
  const [skillNewDesc, setSkillNewDesc] = useState("");
  const [skillLoaded, setSkillLoaded] = useState(false);

  // 运行状态（agent 运行环境检查）— 打开 Diagnostics 时按需检测一次，不常驻轮询
  type DocColor = "green" | "yellow" | "red";
  interface DocCard {
    key: string;
    label: string;
    desc: string;
    color: DocColor;
    title: string;
    detail?: string;
  }
  const [docCards, setDocCards] = useState<DocCard[]>([]);
  const [docBusy, setDocBusy] = useState(false);

  const refreshDoc = useCallback(async () => {
    setDocBusy(true);
    const cards: DocCard[] = [];

    // 后台引擎 agentd — 运行命令 / 读写文件 / 调用模型的本地服务
    try {
      const alive = await pingAgentd({ timeoutMs: 4000 });
      cards.push({
        key: "agentd",
        label: "后台引擎",
        desc: "Fnix 的本地后台服务，负责执行命令、读写文件与调用模型。它必须在线，否则所有 agent 功能都无法使用。",
        color: alive ? "green" : "red",
        title: alive ? "已就绪" : "离线",
        detail: alive ? undefined : "需要启动后端服务：python -m uvicorn fnixagent.main:app --port 8003",
      });
    } catch {
      cards.push({
        key: "agentd",
        label: "后台引擎",
        desc: "Fnix 的本地后台服务，负责执行命令、读写文件与调用模型。它必须在线，否则所有 agent 功能都无法使用。",
        color: "red",
        title: "离线",
        detail: "无法连接 agentd",
      });
    }

    // ~/.fnix + sidecar（harness 状态）
    let st: Awaited<ReturnType<typeof fetchHarnessStatus>>;
    try {
      st = await fetchHarnessStatus();
    } catch {
      st = null;
    }
    const homeExists = st?.home_dir?.exists;
    cards.push({
      key: "~/.fnix",
      label: "配置目录",
      desc: "Fnix 存放设置、记忆与技能的本地文件夹（位于你的用户目录下）。首次运行会自动创建。",
      color: typeof homeExists === "boolean" ? (homeExists ? "green" : "red") : "red",
      title:
        typeof homeExists === "boolean" ? (homeExists ? "已创建" : "尚未创建") : "无法检测",
      detail:
        typeof homeExists === "boolean"
          ? homeExists
            ? st?.home_dir?.path
            : "运行一次后端服务即可自动生成"
          : "后端未响应，请先确认后台引擎在线",
    });
    const sidecarAvail = st?.sidecar?.available;
    cards.push({
      key: "sidecar",
      label: "增强组件",
      desc: "可选的本地辅助进程，提供更快的文件检索与预览等能力。缺失时核心功能仍可用，仅部分体验会降级。",
      color: typeof sidecarAvail === "boolean" ? (sidecarAvail ? "green" : "yellow") : "yellow",
      title:
        typeof sidecarAvail === "boolean" ? (sidecarAvail ? "已连接" : "未启用") : "无法检测",
      detail:
        typeof sidecarAvail === "boolean"
          ? sidecarAvail
            ? st?.sidecar?.url
            : "本地未运行增强组件，能力受限"
          : "后端未响应，请先确认后台引擎在线",
    });

    // LLM Key
    const hasKey = providers.some((p) => Boolean(p.apiKey?.trim()));
    cards.push({
      key: "LLM Key",
      label: "模型密钥",
      desc: "用于调用大语言模型的 API 密钥，仅保存在你本机。没有它就无法生成任何回答。",
      color: hasKey ? "green" : "yellow",
      title: hasKey ? "已配置" : "未配置",
      detail: hasKey ? undefined : "请在「模型」中填写 API Key",
    });

    setDocCards(cards);
    setDocBusy(false);
  }, [providers]);

  useEffect(() => {
    if (section === "diagnostics") void refreshDoc();
  }, [section, refreshDoc]);

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
      setMcpLoaded(true);
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
      setMemLoaded(true);
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
      setSkillLoaded(true);
    }
  }, [skillFilter]);

  /** Load the *real* backend model config so the form reflects what's actually set. */
  const refreshModels = useCallback(async () => {
    setModelsLoaded(false);
    try {
      const cfg = await loadHarnessConfig();
      if (cfg?.provider) setProvider(cfg.provider);
      if (cfg?.model) setModel(cfg.model);
      if (cfg?.base_url) setBaseUrl(cfg.base_url);
      if (cfg?.has_api_key && cfg?.key_hint) setKeyHint(cfg.key_hint);
    } catch {
      /* keep local defaults */
    } finally {
      setModelsLoaded(true);
    }
  }, []);

  /** Add an MCP server to ~/.fnix/mcp.json, then refresh the trust list.
   *  name/command/url 由调用方传入（表单「添加服务器」或「样例模板」导入共用）。*/
  const addMcpServer = async (name: string, command: string, url: string) => {
    const n = name.trim();
    if (!n) {
      setMcpError("服务器名称不能为空");
      return;
    }
    setMcpAdding(true);
    setMcpError(null);
    try {
      const cur = await fetchMcpConfig();
      if (!cur.ok) {
        setMcpError(cur.error || "读取 MCP 配置失败");
        return;
      }
      const servers = (cur.servers || []).filter((s) => s.name !== n);
      const next: McpServerConfig = { name: n, enabled: true };
      if (url.trim()) {
        next.url = url.trim();
      } else {
        const parts = command.trim().split(/\s+/).filter(Boolean);
        next.command = parts[0];
        next.args = parts.slice(1);
      }
      servers.push(next);
      const res = await updateMcpConfig({ version: cur.version ?? 1, servers });
      if (!res.ok) {
        setMcpError(res.error || "写入 MCP 配置失败");
        return;
      }
      setMcpAddName("");
      setMcpAddCmd("");
      setMcpAddUrl("");
      setMcpAddOpen(false);
      setToast(`已添加 ${n}（待授权）`);
      await refreshMcp();
    } finally {
      setMcpAdding(false);
    }
  };

  const handleAddMcp = () => void addMcpServer(mcpAddName, mcpAddCmd, mcpAddUrl);

  /** 从样例模板一键导入（命令拼回字符串，复用 addMcpServer 的写入 + 信任刷新）。*/
  const handleImportTemplate = (tpl: typeof MCP_TEMPLATES[number]) => {
    void addMcpServer(tpl.name, tpl.url ? "" : `${tpl.command} ${tpl.args.join(" ")}`, tpl.url ?? "");
  };

  useEffect(() => {
    if (section === "models") void refreshModels();
  }, [section, refreshModels]);

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
    name: MODEL_PRESETS.find((p) => p.id === provider)?.name || provider,
    apiKey: apiKey.trim(),
    baseUrl: baseUrl.trim() || LOCAL_LLM.baseUrl,
    models: [{ id: model.trim() || LOCAL_LLM.model, name: model.trim() || LOCAL_LLM.model, enabled: true }],
  });

  const handleSave = async () => {
    setSaving(true);
    setToast(null);
    try {
      const prov = buildProvider();
      const list = [prov];
      await saveAIProviders(list);
      onProvidersChange(list);
      const nextConfig: AppConfig = {
        ...config,
        provider: provider,
        model: prov.models[0].id,
        api_key: prov.apiKey,
      };
      await saveConfigToStore(nextConfig);
      onConfigChange(nextConfig);
      await syncHarnessConfig({
        provider: provider,
        model: nextConfig.model,
        base_url: prov.baseUrl,
        api_key: prov.apiKey,
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
      const prov = buildProvider();
      const modelId = prov.models.find((m) => m.enabled)?.id || prov.models[0]?.id || model;
      const harness = await testHarnessLlm({
        provider: provider,
        model: modelId,
        base_url: prov.baseUrl,
        api_key: prov.apiKey,
      });
      if (harness.ok) {
        setTestOk(true);
        setToast("连接成功");
        return;
      }
      // Fallback: direct provider call (may hit CORS in browser)
      const res = await testConnection(prov, modelId);
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
        <div className="fnix-set-head-l">
          <button type="button" className="fnix-set-back" onClick={onClose} aria-label="返回">
            <ArrowLeft size={18} />
          </button>
          <div className="fnix-set-head-t">
            <h1>{SECTION_META[section].title}</h1>
            <p>{SECTION_META[section].desc}</p>
          </div>
        </div>
        <div className="fnix-set-head-r">
          {toast && <span className={`fnix-set-toast${testOk === false ? " bad" : ""}`}>{toast}</span>}
          <button type="button" className="fnix-set-save primary" disabled={saving} onClick={() => void handleSave()}>
            {saving ? <Loader2 size={14} className="spin" /> : null}
            Save
          </button>
        </div>
      </header>

      <div className="fnix-set-body">
        <nav className="fnix-set-nav">
          {NAV_GROUPS.map((grp, gi) => (
            <div className="fnix-set-nav-grp" key={grp.label}>
              {gi > 0 ? <div className="fnix-set-nav-sep" /> : null}
              <span className="fnix-set-nav-group">{grp.label}</span>
              {grp.items.map(([id, label]) => {
                const Icon = SECTION_META[id].icon;
                return (
                  <button
                    key={id}
                    type="button"
                    className={`fnix-set-nav-item${section === id ? " on" : ""}`}
                    onClick={() => setSection(id)}
                  >
                    <Icon size={16} />
                    <span>{label}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <main className="fnix-set-main">
          {section === "models" && (
            <>
              <div className="fnix-set-title">
                <SectionHeader section="models" />
                {!modelsLoaded ? <p className="fnix-field-hint">正在从后端读取当前模型配置…</p> : null}
              </div>

              <div className="fnix-prov-detail">
                <div className="fnix-prov-head">
                  <span className="fnix-prov-avatar" aria-hidden>
                    {PROVIDER_GLYPH[provider] ?? (MODEL_PRESETS.find((p) => p.id === provider)?.name || provider).slice(0, 1).toUpperCase()}
                  </span>
                  <div className="fnix-prov-id">
                    <b>{MODEL_PRESETS.find((p) => p.id === provider)?.name || provider}</b>
                    <span>本地 LLM 提供商 · 密钥仅存本机</span>
                  </div>
                  {testOk === true ? (
                    <span className="fnix-conn-status ok"><CheckCircle2 size={13} /> 已连接</span>
                  ) : testOk === false ? (
                    <span className="fnix-conn-status err"><XCircle size={13} /> 连接失败</span>
                  ) : null}
                </div>
                <div className="fnix-field">
                  <label>Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => {
                      const id = e.target.value;
                      setProvider(id);
                      const preset = MODEL_PRESETS.find((p) => p.id === id);
                      if (preset && preset.baseUrl) {
                        setBaseUrl(preset.baseUrl);
                        if (preset.model) setModel(preset.model);
                      }
                    }}
                    className="fnix-select"
                  >
                    {MODEL_PRESETS.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                  {keyHint ? (
                    <p className="fnix-hint-ok">
                      后端已配置密钥（{keyHint}），保存时将同步写入本机。
                    </p>
                  ) : null}
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
              <SectionHeader section="mcp" />
              <div className="fnix-set-actions" style={{ marginTop: 12 }}>
                <button
                  type="button"
                  className="fnix-set-save"
                  disabled={mcpBusy}
                  onClick={() => setMcpAddOpen((v) => !v)}
                >
                  {mcpAddOpen ? "收起" : "+ 添加服务器"}
                </button>
                <button
                  type="button"
                  className="fnix-set-save ghost"
                  disabled={mcpBusy}
                  onClick={() => void refreshMcp()}
                >
                  {mcpBusy ? <Loader2 size={14} className="spin" /> : null}
                  刷新
                </button>
              </div>

              {mcpAddOpen ? (
                <div className="fnix-add-card">
                  <div className="fnix-field">
                    <label>服务器名称</label>
                    <input
                      value={mcpAddName}
                      placeholder="my-server"
                      onChange={(e) => setMcpAddName(e.target.value)}
                    />
                  </div>
                  <div className="fnix-field">
                    <label>启动命令</label>
                    <input
                      value={mcpAddCmd}
                      placeholder="npx -y @modelcontextprotocol/server-filesystem ."
                      disabled={Boolean(mcpAddUrl.trim())}
                      onChange={(e) => setMcpAddCmd(e.target.value)}
                    />
                  </div>
                  <div className="fnix-field">
                    <label>或 远程 URL（二选一）</label>
                    <input
                      value={mcpAddUrl}
                      placeholder="https://…"
                      disabled={Boolean(mcpAddCmd.trim())}
                      onChange={(e) => setMcpAddUrl(e.target.value)}
                    />
                  </div>
                  {mcpError ? <p className="fnix-hint-err">{mcpError}</p> : null}
                  <div className="fnix-set-actions">
                    <button
                      type="button"
                      className="fnix-set-save"
                      disabled={mcpAdding}
                      onClick={() => void handleAddMcp()}
                    >
                      {mcpAdding ? <Loader2 size={14} className="spin" /> : null}
                      添加并刷新
                    </button>
                    <button
                      type="button"
                      className="fnix-set-save ghost"
                      onClick={() => setMcpAddOpen(false)}
                    >
                      取消
                    </button>
                  </div>
                </div>
              ) : null}

              {!mcpLoaded ? (
                <div className="fnix-loading-row">正在加载 MCP 授权列表…</div>
              ) : mcpError ? (
                <div className="fnix-info-card" style={{ marginTop: 12 }}>
                  <b>无法加载信任台账</b>
                  <span>{mcpError}</span>
                </div>
              ) : mcpServers.length === 0 ? (
                <div className="fnix-empty-card">
                  <b>还没有任何 MCP 服务器</b>
                  <span>点击上方「+ 添加服务器」登记一个本地 / 远程 MCP 服务，批准后即可连接。</span>
                </div>
              ) : (
                <div style={{ marginTop: 8 }}>
                  {mcpServers.map((row) => (
                    <div key={row.name} className="fnix-mcp-row">
                      <span className={`fnix-mcp-dot ${MCP_DOT[row.trust_status] ?? "yellow"}`} aria-hidden />
                      <div className="fnix-mcp-meta">
                        <div className="fnix-mcp-head">
                          <b>{row.name}</b>
                          <span className="fnix-transport">
                            {row.command ? "stdio" : "http"}
                          </span>
                        </div>
                        <span>
                          {row.command
                            ? [row.command, ...(row.args || [])].join(" ")
                            : row.url || "—"}
                        </span>
                        <span className={`fnix-mcp-badge ${row.trust_status}`}>
                          {MCP_STATUS_LABEL[row.trust_status] ?? row.trust_status}
                        </span>
                      </div>
                      <div className="fnix-mcp-actions">
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={mcpBusy || row.trust_status === "approved"}
                          onClick={() => void handleApproveMcp(row)}
                        >
                          授权
                        </button>
                        <button
                          type="button"
                          className="fnix-set-save ghost"
                          disabled={mcpBusy || row.trust_status === "denied"}
                          onClick={() => void handleDenyMcp(row)}
                        >
                          拒绝
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="fnix-mcp-samples">
                <div className="fnix-mcp-samples-head">
                  <b>样例模板</b>
                  <span>一键导入常见 MCP 服务器；导入后需点击「授权」方可连接（fail-closed 本地授权）。</span>
                </div>
                <div className="fnix-mcp-samples-grid">
                  {MCP_TEMPLATES.map((tpl) => {
                    const imported = mcpServers.some((s) => s.name === tpl.name);
                    return (
                      <div key={tpl.name} className="fnix-mcp-sample-card">
                        <div className="fnix-mcp-sample-top">
                          <b>{tpl.name}</b>
                          <span className="fnix-transport">{tpl.url ? "http" : "stdio"}</span>
                        </div>
                        <p className="fnix-mcp-sample-desc">{tpl.desc}</p>
                        <code className="fnix-mcp-sample-cmd">{tpl.url || [tpl.command, ...tpl.args].join(" ")}</code>
                        <button
                          type="button"
                          className="fnix-set-save"
                          disabled={mcpBusy || imported}
                          onClick={() => handleImportTemplate(tpl)}
                        >
                          {imported ? "已导入" : "导入"}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {section === "memory" && (
            <div className="fnix-set-title">
              <SectionHeader section="memory" />
              {!memLoaded ? <div className="fnix-loading-row">正在加载记忆统计…</div> : null}
              <div className="fnix-mem-grid">
                <div className="fnix-mem-layer">
                  <div className="fnix-mem-layer-top">
                    <span className="fnix-mem-ico"><Zap size={15} /></span>
                    <b>短期记忆</b>
                  </div>
                  <div className="fnix-mem-layer-val">{memStats?.short_term_count ?? "—"}<i>条</i></div>
                  <div className="fnix-mem-layer-sub">{memStats?.short_term_tokens ?? 0} tokens · 会话内上下文</div>
                </div>
                <div className="fnix-mem-layer">
                  <div className="fnix-mem-layer-top">
                    <span className="fnix-mem-ico"><Brain size={15} /></span>
                    <b>长期记忆</b>
                  </div>
                  <div className="fnix-mem-layer-val">{memStats?.long_term_count ?? "—"}<i>条</i></div>
                  <div className="fnix-mem-layer-sub">语义检索可用 · 跨会话保留</div>
                </div>
                <div className="fnix-mem-layer">
                  <div className="fnix-mem-layer-top">
                    <span className="fnix-mem-ico"><Boxes size={15} /></span>
                    <b>实体记忆</b>
                  </div>
                  <div className="fnix-mem-layer-val">{memStats?.entity_count ?? "—"}<i>个</i></div>
                  <div className="fnix-mem-layer-sub">
                    {memStats?.entity_types && Object.keys(memStats.entity_types).length > 0
                      ? "类型: " + Object.entries(memStats.entity_types).map(([k, v]) => `${k}=${v}`).join(" · ")
                      : "暂无已识别实体"}
                  </div>
                </div>
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
                    检索
                  </button>
                </div>
                {memError ? <p className="fnix-hint-err">{memError}</p> : null}
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
                  刷新统计
                </button>
                <button
                  type="button"
                  className="fnix-set-save"
                  disabled={memBusy}
                  onClick={() => void handleMemCleanup()}
                >
                  清理过期
                </button>
              </div>
            </div>
          )}

          {section === "skills" && (
            <div className="fnix-set-title">
              <SectionHeader section="skills" />
              {(() => {
                const builtinCount = skillEntries.filter((e) => e.owner_id === "builtin").length;
                return (
                  <>
                    <div className="fnix-skill-sample">
                      <Sparkles size={15} />
                      <span>
                        已内置 <b>{builtinCount}</b> 个开箱即用技能样板。点击「创建草稿」自定义，或导入你自己的技能（SKILL.md）。
                      </span>
                    </div>

                    <div className="fnix-field" style={{ marginTop: 14 }}>
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
                          创建草稿
                        </button>
                      </div>
                    </div>

                    <div className="fnix-field" style={{ marginTop: 12 }}>
                      <label>状态过滤</label>
                      <div className="fnix-seg" style={{ maxWidth: "100%", overflowX: "auto" }}>
                        {SKILL_FILTERS.map((f) => (
                          <button
                            key={f.value}
                            type="button"
                            className={`fnix-seg-item ${skillFilter === f.value ? "on" : ""}`}
                            onClick={() => setSkillFilter(f.value)}
                          >
                            {f.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {skillError ? (
                      <div className="fnix-info-card" style={{ marginTop: 12 }}>
                        <b>Error</b>
                        <span>{skillError}</span>
                      </div>
                    ) : null}

                    {skillEntries.length === 0 && !skillError ? (
                      !skillLoaded ? (
                        <div className="fnix-loading-row">正在加载技能…</div>
                      ) : (
                        <div className="fnix-empty-card">
                          <b>还没有技能</b>
                          <span>在上方填写名称创建第一个草稿，进入 DRAFT → 审核 → 发布 的生命周期。</span>
                        </div>
                      )
                    ) : (
                      <div className="fnix-skill-grid" style={{ marginTop: 12 }}>
                        {skillEntries.map((entry) => (
                          <div
                            key={entry.id}
                            className={`fnix-skill-card${entry.owner_id === "builtin" ? " is-sample" : ""}`}
                          >
                            <div className="fnix-skill-card-head">
                              <span className="fnix-skill-ico"><Boxes size={16} /></span>
                              <div className="fnix-skill-titles">
                                <div className="fnix-skill-name-row">
                                  <b>{entry.display_name || entry.name}</b>
                                  <span className="fnix-skill-ver">v{entry.latest_version || "—"}</span>
                                </div>
                                <span className="fnix-skill-id">{entry.name}</span>
                              </div>
                              <div className="fnix-skill-badges">
                                {entry.owner_id === "builtin" ? (
                                  <span className="fnix-skill-builtin">内置样板</span>
                                ) : null}
                                <span className={`fnix-mcp-badge ${entry.status}`}>
                                  {SKILL_STATUS_LABEL[entry.status] ?? entry.status}
                                </span>
                              </div>
                            </div>
                            {entry.description ? <p className="fnix-skill-desc">{entry.description}</p> : null}
                            <div className="fnix-skill-meta">
                              <span className="fnix-chip">{entry.category || "通用"}</span>
                              {entry.tags?.length ? (
                                <div className="fnix-skill-tags">
                                  {entry.tags.slice(0, 4).map((t) => (
                                    <span className="fnix-skill-tag" key={t}>#{t}</span>
                                  ))}
                                </div>
                              ) : null}
                            </div>
                            <div className="fnix-skill-actions">
                              {entry.status === "draft" ? (
                                <button
                                  type="button"
                                  className="fnix-set-save"
                                  disabled={skillBusy}
                                  onClick={() => void handleSkillAction(entry, "submit")}
                                >
                                  提交
                                </button>
                              ) : null}
                              {entry.status === "pending_review" ? (
                                <button
                                  type="button"
                                  className="fnix-set-save"
                                  disabled={skillBusy}
                                  onClick={() => void handleSkillAction(entry, "approve")}
                                >
                                  通过
                                </button>
                              ) : null}
                              {entry.status === "published" ? (
                                <button
                                  type="button"
                                  className="fnix-set-save ghost"
                                  disabled={skillBusy}
                                  onClick={() => void handleSkillAction(entry, "deprecate")}
                                >
                                  弃用
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
                  </>
                );
              })()}
            </div>
          )}

          {section === "diagnostics" && (
            <div className="fnix-set-title">
              <SectionHeader section="diagnostics" />
              {(() => {
                const hasRed = docCards.some((c) => c.color === "red");
                const hasYellow = docCards.some((c) => c.color === "yellow");
                const overall: "ok" | "limited" | "down" = hasRed
                  ? "down"
                  : hasYellow
                    ? "limited"
                    : "ok";
                const detecting = docCards.length === 0;
                const headline = detecting
                  ? "正在检测 Fnix 运行状态…"
                  : overall === "ok"
                    ? "一切正常，可以开始使用"
                    : overall === "limited"
                      ? "可以正常使用，部分增强功能暂不可用"
                      : "暂时无法使用，请按下方提示检查";
                const agentdDown = docCards.find((c) => c.key === "agentd")?.color === "red";
                const FRIENDLY: Record<string, string> = {
                  "agentd": "服务未运行，请重启 Fnix 客户端后重试。",
                  "~/.fnix": "配置目录缺失，重启客户端即可自动生成。",
                  "sidecar": "部分增强功能（更快的文件检索与预览）暂不可用，核心功能不受影响。",
                  "LLM Key": "尚未配置模型密钥：前往「模型」填写 API Key 后即可正常对话。",
                };
                const actionable: string[] = docCards
                  .filter((c) => c.color !== "green")
                  .filter((c) => !(agentdDown && (c.key === "~/.fnix" || c.key === "sidecar")))
                  .map((c) => FRIENDLY[c.key])
                  .filter((m): m is string => typeof m === "string");
                return (
                  <div className="fnix-diag">
                    <div className="fnix-diag-summary">
                      <span
                        className={`fnix-diag-dot ${
                          docCards.length === 0
                            ? "idle"
                            : overall === "ok"
                              ? "green"
                              : overall === "limited"
                                ? "yellow"
                                : "red"
                        }`}
                      />
                      <span className="fnix-diag-summary-text">{headline}</span>
                      <button
                        type="button"
                        className="fnix-set-save ghost"
                        disabled={docBusy}
                        onClick={() => void refreshDoc()}
                      >
                        {docBusy ? "检测中…" : "重新检测"}
                      </button>
                    </div>

                    {actionable.length > 0 && (
                      <div className="fnix-diag-action">
                        {actionable.map((m, i) => (
                          <p key={i}>{m}</p>
                        ))}
                      </div>
                    )}

                    <div className="fnix-set-actions" style={{ marginTop: 4 }}>
                      <button type="button" className="fnix-set-save" onClick={() => onOpenBenchmark?.()}>
                        打开全链路测试面板
                      </button>
                    </div>

                    <details className="fnix-diag-advanced">
                      <summary>高级诊断（开发者）</summary>
                      <div className="fnix-diag-grid">
                        {docCards.map((c) => (
                          <div key={c.key} className="fnix-diag-card">
                            <div className="fnix-diag-card-top">
                              <b>{c.label}</b>
                              <span className={`fnix-diag-dot ${c.color}`} />
                            </div>
                            <span className={`fnix-diag-status ${c.color}`}>{c.title}</span>
                            <span className="fnix-diag-desc">{c.desc}</span>
                            {c.detail ? <span className="fnix-diag-detail">{c.detail}</span> : null}
                          </div>
                        ))}
                      </div>
                      <div className="fnix-set-actions" style={{ marginTop: 8 }}>
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
                      </div>
                      {doctor && (
                        <div className="fnix-info-card" style={{ marginTop: 12 }}>
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
                    </details>
                  </div>
                );
              })()}
            </div>
          )}

          {section === "general" && (
            <div className="fnix-set-title">
              <SectionHeader section="general" />

              <div className="fnix-set-card">
                <div className="fnix-set-card-head">
                  <div>
                    <b>外观</b>
                    <span>界面外观（浅色 / 深色）跟随系统设置；高对比度与减弱动效自动适配系统无障碍偏好。</span>
                  </div>
                </div>
              </div>

              <div className="fnix-set-card">
                <div className="fnix-set-card-head">
                  <div>
                    <b>当前模型</b>
                    <span>本地推理默认使用的模型与供应商。</span>
                  </div>
                </div>
                <div className="fnix-model-row">
                  <span className="fnix-model-dot" aria-hidden />
                  <div className="fnix-model-meta">
                    <b>{model || LOCAL_LLM.model}</b>
                    <span>{LOCAL_LLM.providerName}</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {section === "about" && (
            <div className="fnix-set-title">
              <SectionHeader section="about" />

              <div className="fnix-about-intro">
                <b className="fnix-changelog-title">产品能力</b>
                <p>Fnix 是一个本地优先的编码智能体工作台，开箱即用：</p>
                <ul>
                  <li><b>对话与执行</b>：直接提问、写代码、跑命令，结果落盘到你的工作区。</li>
                  <li><b>本地记忆</b>：短期对话窗口 + 长期向量记忆 + 实体画像，数据存本机。</li>
                  <li><b>技能与连接</b>：Skills 生命周期管理，MCP 服务器本地授权（fail-closed）。</li>
                </ul>
                <details className="fnix-evo-note">
                  <summary>进化内核（KTG / STP / MFP）是什么？</summary>
                  <p>Fnix 在每轮回答时运行一个自进化内核，为主对话提供参考上下文：</p>
                  <ul>
                    <li><b>KTG</b>（知识路径）：从知识图谱检索到的相关推理路径数量。</li>
                    <li><b>STP</b>（概念识别）：本轮任务识别并采用的核心概念。</li>
                    <li><b>MFP</b>（历史经验）：实际参考的短期与长期记忆条数。</li>
                  </ul>
                  <p className="fnix-evo-hint">
                    这些信息原先显示在对话底部，为保持界面简洁已统一收纳在「关于」中。实时数值会在会话进行中由运行时生成。
                  </p>
                </details>
              </div>

              <div className="fnix-about-hero">
                <div className="fnix-about-logo" aria-hidden>
                  <Sparkles size={20} color="#fff" strokeWidth={2.2} />
                </div>
                <div className="fnix-about-meta">
                  <b>FnixAgent Workbench</b>
                  <span>v{FNIX_VERSION} · {FNIX_BUILD_NUMBER}</span>
                </div>
                <span className={`fnix-rel-badge${FNIX_RELEASE_CHANNEL === "internal" ? " internal" : ""}`}>
                  {FNIX_RELEASE_CHANNEL === "internal" ? "内部测试" : FNIX_RELEASE_CHANNEL}
                </span>
              </div>

              <div className="fnix-info-card">
                <b>发布渠道</b>
                <span>当前为 internal（内部测试）构建，尚未发布公开 Release。功能仍在本地验证中。</span>
              </div>

              <div className="fnix-rel-card">
                <div className="fnix-rel-head">
                  <b>Release 下载</b>
                  <span>{FNIX_RELEASE_DATE} 构建 · 暂未发布</span>
                </div>
                <p className="fnix-rel-note">
                  正式版将通过发布渠道提供直接下载。当前内部测试版本暂未打包 Release，请先用本地构建验证，暂不接入外部发布。
                </p>
                <div className="fnix-set-actions">
                  <button
                    type="button"
                    className="fnix-set-save ghost"
                    onClick={() => setToast("当前为内部测试版本，暂未发布 Release")}
                  >
                    检查更新
                  </button>
                </div>
              </div>

              <div className="fnix-info-card">
                <b>本地模型</b>
                <span>{LOCAL_LLM.providerName} · {model || LOCAL_LLM.model}</span>
              </div>

              <div className="fnix-changelog">
                <b className="fnix-changelog-title">更新日志</b>
                <ul>
                  {FNIX_CHANGELOG.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>

              <div className="fnix-info-card">
                <b>许可证</b>
                <span>{FNIX_LICENSE} · 配置与密钥均存储于本机</span>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
