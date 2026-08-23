/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Fnix Desktop shell — Desktop-client look (Chat + Code).
 * Layout mirrors OpenAI Desktop desktop (sidebar + centered composer), not Google apps.
 * Runtime is Fnix BYOK.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import {
  Activity,
  BookOpen,
  ChevronDown,
  FolderOpen,
  GitCompare,
  Globe,
  Layers,
  LayoutPanelLeft,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
  Plus,
  Settings as SettingsIcon,
  SquareTerminal,
  X,
} from 'lucide-react';
import { ProductSegment } from './ModeSegment';
import {
  ensureFnixWorkspace,
  getFnixApiBase,
  pingAgentd,
  syncHarnessConfig,
} from '../../lib/fnixBridge';
import { indexHarnessWorkspace, pickFnixLlm } from './fnixRuntime';
import type { AIProviderConfig } from '../../utils/providers';
import {
  addRecentProject,
  loadAIProviders,
  loadConfigFromStore,
  loadRecentProjectPath,
  loadRecentProjects,
  renameRecentProject,
  saveAIProviders,
  saveConfigToStore,
  saveRecentProjectPath,
  setProjectRoot,
  type AppConfig,
  type ChatAttachment,
  type RecentProject,
} from '../../utils/tauri';
import { loadAllChatSessions, initChatDb } from '../../services/persistence/chatDb';
import { Composer } from './Composer';
// 进化辅助信息（KTG/STP/MFP）已移至设置 → Diagnostics「进化内核」卡片
import { FnixStatusBar } from './FnixStatusBar';
import { MessageList } from './MessageList';
import { DesktopSettings } from './DesktopSettings';
import { FullChainBenchmarkPanel } from './FullChainBenchmarkPanel';
import { OnboardingWizard, isOnboardingDone, markOnboardingDone } from './OnboardingWizard';
import { ProcessTimeline } from './ProcessTimeline';
import { ProjectHome, ProjectsLibrary, projectDisplayName } from './ProjectsPane';
import { ReviewView } from './ReviewView';
import { ResultsView } from './ResultsView';
import { WorkModePicker, workModePlaceholder } from './WorkModePicker';
import {
  hasLocalLlmBootstrap,
  LOCAL_LLM,
  localAppConfig,
  localProviderConfig,
  updateLocalLlm,
  refreshLocalLlmFromAgentd,
} from './localLlm';
import { isBenchmarkPrompt } from '../../services/benchmark/fullChainBenchmark';
import { useChatFlow, type ShellMode, type WorkExecMode } from './useChatFlow';
import { isTauriDesktop, setDesktopWindowTitle } from './desktopEnv';
import { useShellHotkeys } from './useShellHotkeys';
import { useSessionStore } from './sessionStore';
import { useWorkspaceStore } from './workspaceStore';
import { useReviewStore } from './reviewStore';
import { canOpenReview } from './shellFsm';
import { ThreadSidebar, type ThreadWithWorkspace } from './ThreadSidebar';
import { TaskBoard } from './TaskBoard';
import { useJobsStore } from './useJobsStore';
import { CanvasView } from './CanvasView';
import { TerminalView } from './TerminalView';
import { BrowserView } from './BrowserView';
import { StudioPanel, type StudioTabDef } from './StudioPanel';
import { assessReviewBatch } from './reviewRisk';
import type { StudioTab } from './sessionStore';
import { SkillManager } from './SkillManager';
import { CommandPalette } from './CommandPalette';
import { ShortcutCheatsheet } from './ShortcutCheatsheet';
import { resolveShellTheme, type ShellThemeResolved } from './theme';
import './tokens.css';
/* Glass kit after shell tokens so frost styles win under .fnix-glass */
import '../../ui/glass';

const IS_DESKTOP = isTauriDesktop();

const DEFAULT_CONFIG: AppConfig = {
  provider: LOCAL_LLM.provider || 'qwen',
  api_key: '',
  model: LOCAL_LLM.model || 'qwen-plus-2025-07-28',
  theme: 'system',
};

function extractCodeBlocks(text: string): { lang: string; body: string }[] {
  const out: { lang: string; body: string }[] = [];
  const re = /```(\w*)\n?([\s\S]*?)```/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push({ lang: m[1] || 'code', body: m[2].trimEnd() });
  }
  return out;
}

const WORK_MODE_STORE = 'fnix-work-modes';

function loadWorkModeForThread(storageKey: string, threadId: string): WorkExecMode | null {
  try {
    const raw = localStorage.getItem(`${WORK_MODE_STORE}:${storageKey}`);
    if (!raw) return null;
    const map = JSON.parse(raw) as Record<string, WorkExecMode>;
    const m = map[threadId];
    return m === 'ask' || m === 'plan' || m === 'craft' ? m : null;
  } catch {
    return null;
  }
}

function saveWorkModeForThread(storageKey: string, threadId: string, mode: WorkExecMode) {
  try {
    const key = `${WORK_MODE_STORE}:${storageKey}`;
    const raw = localStorage.getItem(key);
    const map = raw ? (JSON.parse(raw) as Record<string, WorkExecMode>) : {};
    map[threadId] = mode;
    localStorage.setItem(key, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

/**
 * ChatHead — Work / Code session 共用的顶部工具栏。
 * 抽取自原 Work session 和 Code session 重复的 chat-head 结构（~50 行 × 2）。
 * 按钮统一顺序：侧栏 · [jobs?] [skills] [inspector] [projectChip?] [newChat]
 */
interface ChatHeadProps {
  onToggleAside: () => void;
  onNewChat: () => void;
  skillsOpen: boolean;
  onToggleSkills: () => void;
  /** Studio Panel（右侧统一工作台面）开关 */
  inspectorOpen: boolean;
  onToggleInspector: () => void;
  /** Inspector 徽章计数（Code = 待确认变更数）*/
  inspectorBadge?: number;
  /** Inspector 评审风险色点 */
  inspectorDot?: 'low' | 'medium' | 'high';
  /** Work 模式专属：并行任务面板开关 */
  jobsOpen?: boolean;
  activeJobCount?: number;
  onToggleJobs?: () => void;
  projectPath?: string;
  projectLabel?: string;
  onOpenProject: () => void;
}

function ChatHead({
  onToggleAside,
  onNewChat,
  skillsOpen,
  onToggleSkills,
  inspectorOpen,
  onToggleInspector,
  inspectorBadge,
  inspectorDot,
  jobsOpen,
  activeJobCount,
  onToggleJobs,
  projectPath,
  projectLabel,
  onOpenProject,
}: ChatHeadProps) {
  return (
    <div className="fnix-chat-head">
      <button type="button" className="fnix-ibtn sm" title="侧栏" onClick={onToggleAside}>
        <LayoutPanelLeft size={16} />
      </button>
      <div style={{ display: 'flex', gap: 2, alignItems: 'center', marginLeft: 'auto' }}>
        {onToggleJobs ? (
          <button
            type="button"
            className={`fnix-ibtn sm${jobsOpen ? ' active' : ''}`}
            onClick={onToggleJobs}
            title="任务面板"
          >
            <Layers size={16} />
            {activeJobCount ? <span className="fnix-ibtn-badge">{activeJobCount}</span> : null}
          </button>
        ) : null}
        <button
          type="button"
          className={`fnix-ibtn sm${skillsOpen ? ' on' : ''}`}
          onClick={onToggleSkills}
          title="技能管理"
        >
          <BookOpen size={15} />
        </button>
        <button
          type="button"
          className={`fnix-ibtn sm${inspectorOpen ? ' on' : ''}`}
          onClick={onToggleInspector}
          title="工作台面 (Ctrl+\)"
        >
          <PanelRight size={16} />
          {inspectorBadge ? <span className="fnix-ibtn-badge">{inspectorBadge}</span> : null}
          {inspectorDot ? <span className={`fnix-ibtn-dot ${inspectorDot}`} aria-hidden /> : null}
        </button>
        <button type="button" className="fnix-ibtn sm" onClick={onNewChat} title="新任务">
          <Plus size={16} />
        </button>
      </div>
    </div>
  );
}

export default function DesktopApp() {
  const mode = useSessionStore((s) => s.mode);
  const setMode = useSessionStore((s) => s.setMode);
  const pane = useSessionStore((s) => s.pane);
  const setPane = useSessionStore((s) => s.setPane);
  const inspectorOpen = useSessionStore((s) => s.inspectorOpen);
  const setInspectorOpen = useSessionStore((s) => s.setInspectorOpen);
  const inspectorTab = useSessionStore((s) => s.inspectorTab);
  const setInspectorTab = useSessionStore((s) => s.setInspectorTab);
  const toggleInspector = useSessionStore((s) => s.toggleInspector);
  const pinArtifact = useSessionStore((s) => s.pinArtifact);
  const pinnedArtifacts = useSessionStore((s) => s.pinnedArtifacts);

  // 本轮运行中用户是否手动开/关过面板 — 手动操作后自动展开不再打扰
  const panelTouchedRef = useRef(false);
  const closeInspector = useCallback(() => {
    panelTouchedRef.current = true;
    setInspectorOpen(false);
  }, [setInspectorOpen]);
  const toggleInspectorUser = useCallback(() => {
    panelTouchedRef.current = true;
    toggleInspector();
  }, [toggleInspector]);

  const projectPath = useWorkspaceStore((s) => s.projectPath);
  const recentProjects = useWorkspaceStore((s) => s.recentProjects);
  const agentdOk = useWorkspaceStore((s) => s.agentdOk);
  const setProjectPath = useWorkspaceStore((s) => s.setProjectPath);
  const setRecentProjects = useWorkspaceStore((s) => s.setRecentProjects);
  const upsertRecent = useWorkspaceStore((s) => s.upsertRecent);
  const setAgentdOk = useWorkspaceStore((s) => s.setAgentdOk);

  const reviewPath = useReviewStore((s) => s.selectedPath);
  const setReviewPath = useReviewStore((s) => s.selectPath);

  /** Ask | Plan | Craft —唯一模式开关（Composer pill）；不再另设 Chat|Work */
  const [workMode, setWorkMode] = useState<WorkExecMode>('craft');
  const [draft, setDraft] = useState('');
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  const [providers, setProviders] = useState<AIProviderConfig[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [showBenchmark, setShowBenchmark] = useState(false);
  const [showOnboarding, setShowOnboarding] = useState(false);
  const [settingsSection, setSettingsSection] = useState<
    'general' | 'models' | 'about' | 'diagnostics' | 'mcp'
  >('models');
  const [booted, setBooted] = useState(false);
  const [hintDismissed, setHintDismissed] = useState(() => {
    try {
      return localStorage.getItem('fnix.web-hint-dismissed') === '1';
    } catch {
      return false;
    }
  });
  const [repoHint, setRepoHint] = useState(false);
  const [asideOpen, setAsideOpen] = useState(true);
  const [jobsOpen, setJobsOpen] = useState(false);
  const [skillsOpen, setSkillsOpen] = useState(false);

  // 跨工作空间加载所有会话（侧栏分组展示）
  const [allThreads, setAllThreads] = useState<ThreadWithWorkspace[]>([]);
  const [allThreadsTick, setAllThreadsTick] = useState(0);
  const refreshAllThreads = useCallback(() => {
    void (async () => {
      try {
        await initChatDb();
        const rows = await loadAllChatSessions(300);
        const mapped: ThreadWithWorkspace[] = rows.map((r) => {
          // project_path = `${workspace}::${mode}` 或 FALLBACK_WORKSPACE
          const wsPart = r.project_path?.split('::')[0] || '';
          const ws = wsPart === '__fnix_desktop__' ? '' : wsPart;
          return {
            id: r.id,
            title: r.title || '新任务',
            updatedAt: r.updated_at,
            workspace: ws,
            status: 'done' as const,
          };
        });
        setAllThreads(mapped);
      } catch {
        // browser mode: no-op
      }
    })();
  }, []);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [keysOpen, setKeysOpen] = useState(false);

  // 主题：从 config.theme（light/dark/system）解析为实际生效值。
  // 替代原来的硬编码 "light" — 让 DesktopSettings 中的主题切换真正生效。
  // system 偏好下跟随 matchMedia 变化（通过 systemDarkTick 强制 re-render）。
  const [systemDarkTick, setSystemDarkTick] = useState(0);
  useEffect(() => {
    if (config.theme !== 'system') return;
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => setSystemDarkTick((n) => n + 1);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, [config.theme]);
  const themeResolved: ShellThemeResolved = useMemo(
    // eslint-disable-next-line react-hooks/exhaustive-deps
    () => resolveShellTheme(config.theme),
    // systemDarkTick 仅用于 system 模式下强制重算
    [config.theme, systemDarkTick],
  );

  // 多任务并行：订阅活跃 job 数（用于按钮 badge）
  const activeJobCount = useJobsStore(
    (s) => s.jobs.filter((j) => j.status === 'running' || j.status === 'pending').length,
  );

  const chat = useChatFlow({
    workspace: projectPath,
    providers,
    apiKey: config.api_key,
    providerName: config.provider,
    model: config.model,
    mode,
    workMode,
  });

  /** Ask = 纯对话；Plan/Craft = 交付布局（Results / Goal）*/
  const isDeliver = workMode !== 'ask';

  const workStorageKey = `${projectPath || '__fnix_desktop__'}::work`;

  useEffect(() => {
    if (mode !== 'work' || !chat.activeId) return;
    saveWorkModeForThread(workStorageKey, chat.activeId, workMode);
  }, [mode, workStorageKey, chat.activeId, workMode]);

  const openWorkThread = useCallback(
    async (id: string) => {
      setPane('home');
      await chat.openThread(id);
      const saved = loadWorkModeForThread(workStorageKey, id);
      if (saved) setWorkMode(saved);
    },
    [chat, workStorageKey],
  );

  const executePlan = useCallback(() => {
    setWorkMode('craft');
    const msgs = chat.messages;
    const lastUser = [...msgs].reverse().find((m) => m.role === 'user');
    if (lastUser?.content) {
      setDraft(`${lastUser.content}\n\n请按上述计划执行，并用 write_file 落盘到 .fnix/artifacts/`);
    }
  }, [chat.messages]);



  // Ctrl/Cmd+K → 命令面板；? → 快捷键速查（输入框内不劫持）
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if ((e.metaKey || e.ctrlKey) && e.key === '\\') {
        e.preventDefault();
        toggleInspectorUser();
        return;
      }
      if ((e.metaKey || e.ctrlKey) && (e.key === 'b' || e.key === 'B')) {
        e.preventDefault();
        setAsideOpen((v) => !v);
        return;
      }
      if (e.key === '?' && !e.metaKey && !e.ctrlKey && !e.altKey) {
        const t = e.target as HTMLElement | null;
        if (t && t.closest("input, textarea, [contenteditable='true']")) return;
        e.preventDefault();
        setKeysOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [toggleInspectorUser]);

  // 草稿自动保存：按会话持久化，切换会话/刷新不丢
  const draftKey = `fnix-draft:${chat.activeId ?? 'new'}`;
  useEffect(() => {
    try {
      setDraft(localStorage.getItem(draftKey) ?? '');
    } catch {
      /* ignore */
    }
  }, [draftKey]);
  useEffect(() => {
    const t = window.setTimeout(() => {
      try {
        if (draft) localStorage.setItem(draftKey, draft);
        else localStorage.removeItem(draftKey);
      } catch {
        /* ignore */
      }
    }, 250);
    return () => window.clearTimeout(t);
  }, [draftKey, draft]);

  // 任务结束（streaming true→false）后刷新全量任务列表
  const prevStreamingRef = useRef(false);
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current;
    prevStreamingRef.current = chat.streaming;
    if (wasStreaming && !chat.streaming) {
      const t = window.setTimeout(() => setAllThreadsTick((n) => n + 1), 300);
      return () => window.clearTimeout(t);
    }
  }, [chat.streaming]);

  // 初始加载 + streaming 结束后刷新全量任务
  useEffect(() => {
    void refreshAllThreads();
  }, [refreshAllThreads, allThreadsTick]);

  const onProductChange = useCallback(
    (next: ShellMode) => {
      setMode(next);
      setPane('home');
    },
    [setMode, setPane],
  );

  const modelLabel = useMemo(() => {
    const p = providers.find(
      (x) => (x.apiKey && x.apiKey.trim()) || x.name.toLowerCase().includes('ollama'),
    );
    const model = p?.models.find((m) => m.enabled)?.id || p?.models[0]?.id || config.model;
    const raw = model || LOCAL_LLM.model || 'Model';
    // 只显示模型名，去掉 provider 前缀（如 deepseek-ai/）
    const slashIdx = raw.lastIndexOf('/');
    return slashIdx >= 0 ? raw.slice(slashIdx + 1) : raw;
  }, [providers, config.model]);

  const openSettings = useCallback(
    (section: 'general' | 'models' | 'about' | 'diagnostics' | 'mcp' = 'models') => {
      setSettingsSection(section);
      setShowSettings(true);
    },
    [],
  );

  const renameProjectAlias = useCallback(
    async (path: string, alias: string) => {
      const next = await renameRecentProject(path, alias);
      setRecentProjects(next);
    },
    [setRecentProjects],
  );

  /** Composer pill: show active model name; click opens Settings (no model catalog). */
  const modelControl = (
    <button
      type="button"
      className="fnix-pill"
      onClick={() => openSettings('models')}
      title="模型设置"
    >
      {modelLabel} <ChevronDown size={12} />
    </button>
  );

  /** WorkModePicker — Work 模式下放在 Composer 左侧（加号旁边） */
  const workModeControl =
    mode === 'work' ? (
      <WorkModePicker value={workMode} onChange={setWorkMode} disabled={chat.streaming} />
    ) : null;

  const hasByok = useMemo(() => {
    return Boolean(
      pickFnixLlm(providers, config.api_key, config.provider, config.model)?.api_key ||
      providers.some((p) => p.name.toLowerCase().includes('ollama')),
    );
  }, [providers, config.api_key, config.provider, config.model]);

  const projectLabel = useMemo(() => {
    if (!projectPath) return '';
    return projectDisplayName(
      recentProjects.find((p) => p.path === projectPath) || { path: projectPath },
    );
  }, [projectPath, recentProjects]);

  const lastAssistant = useMemo(
    () => [...chat.messages].reverse().find((m) => m.role === 'assistant' && m.content),
    [chat.messages],
  );
  const codeBlocks = useMemo(
    () => (lastAssistant ? extractCodeBlocks(lastAssistant.content) : []),
    [lastAssistant],
  );
  const pendingChanges = chat.fileChanges;
  const hasSession = chat.messages.length > 0;

  /* ── Studio Panel 派生状态 ── */
  // 评审自动展开签名：同一批变更只自动展开一次
  const reviewAutoSigRef = useRef('');
  // Deliver 首个产物自动展开：每轮只触发一次
  const prevArtCountRef = useRef(0);

  // 评审风险（供 ChatHead 徽章色点 + Review tab dot）
  const reviewRisk = useMemo(() => assessReviewBatch(pendingChanges), [pendingChanges]);

  // 新一轮运行开始时重置"用户已手动操作"标记
  useEffect(() => {
    if (chat.streaming) panelTouchedRef.current = false;
  }, [chat.streaming]);

  const workTabs = useMemo<StudioTabDef[]>(
    () => [
      {
        id: 'canvas',
        label: '画布',
        icon: <LayoutPanelLeft size={14} />,
        badge: pinnedArtifacts.length || undefined,
      },
      // BUG-6 fix: Work 模式下 pickChatBackend 可能路由到 Code 管线，
      // 此时 fileChange 事件填充 pendingChanges 但 review tab 不显示，
      // 导致 Accept 按钮不出现、文件不落盘。有 pending changes 时动态注入 review tab。
      ...(pendingChanges.length > 0
        ? [
            {
              id: 'review' as StudioTab,
              label: '评审',
              icon: <GitCompare size={14} />,
              badge: pendingChanges.length || undefined,
              dot: reviewRisk.maxLevel || undefined,
            },
          ]
        : []),
      ...(isDeliver
        ? [
            {
              id: 'results' as StudioTab,
              label: '结果',
              icon: <FolderOpen size={14} />,
              badge: chat.artifacts.length || undefined,
            },
          ]
        : []),
      {
        id: 'terminal' as StudioTab,
        label: '终端',
        icon: <SquareTerminal size={14} />,
        live: chat.streaming,
      },
      { id: 'browser' as StudioTab, label: '浏览器', icon: <Globe size={14} /> },
    ],
    [pinnedArtifacts.length, pendingChanges.length, reviewRisk.maxLevel, isDeliver, chat.artifacts.length, chat.streaming],
  );

  const codeTabs = useMemo<StudioTabDef[]>(
    () => [
      {
        id: 'canvas',
        label: '画布',
        icon: <LayoutPanelLeft size={14} />,
        badge: pinnedArtifacts.length || undefined,
      },
      {
        id: 'review' as StudioTab,
        label: '评审',
        icon: <GitCompare size={14} />,
        badge: pendingChanges.length || undefined,
        dot: pendingChanges.length > 0 ? reviewRisk.maxLevel : undefined,
      },
      {
        id: 'terminal' as StudioTab,
        label: '终端',
        icon: <SquareTerminal size={14} />,
        live: chat.streaming,
      },
      { id: 'browser' as StudioTab, label: '浏览器', icon: <Globe size={14} /> },
    ],
    [pinnedArtifacts.length, pendingChanges.length, reviewRisk.maxLevel, chat.streaming],
  );

  const studioTabs = mode === 'code' ? codeTabs : workTabs;
  // 当前 tab 若不在可见集合中（如 ask↔craft 切换），回落到画布
  const effectiveTab: StudioTab = studioTabs.some((t) => t.id === inspectorTab)
    ? inspectorTab
    : 'canvas';

  useEffect(() => {
    void (async () => {
      try {
        const [cfg, prov, recent, last] = await Promise.all([
          loadConfigFromStore().catch(() => DEFAULT_CONFIG),
          loadAIProviders().catch(() => [] as AIProviderConfig[]),
          loadRecentProjects().catch(() => [] as RecentProject[]),
          loadRecentProjectPath().catch(() => ''),
        ]);
        let nextConfig: AppConfig = { ...DEFAULT_CONFIG, ...cfg };
        let nextProviders = prov;

        // Pull DashScope key + model from agentd (.env) so the pill shows qwen-plus-—
        await refreshLocalLlmFromAgentd().catch(() => undefined);
        if (hasLocalLlmBootstrap()) {
          nextProviders = [localProviderConfig()];
          nextConfig = localAppConfig(nextConfig);
          await saveAIProviders(nextProviders).catch(() => undefined);
          await saveConfigToStore(nextConfig).catch(() => undefined);
          // agentd 可能尚未就绪(慢启动),同步失败不得阻断启动序列,
          // 否则首次运行向导判断会被跳过,用户永远看不到 onboarding。
          await syncHarnessConfig({
            provider: LOCAL_LLM.provider,
            model: nextConfig.model,
            base_url: LOCAL_LLM.baseUrl,
            api_key: nextConfig.api_key,
          }).catch(() => undefined);
        }

        setConfig(nextConfig);
        setProviders(nextProviders);
        setRecentProjects(recent);
        // DEV 测试钩子：浏览器模式经 localStorage["fnix.dev.workspace"] 指定工作区，
        // 供全链路 UI 驱动测试逐项目/逐题隔离工作区。仅在本机 localhost 开发环境生效，
        // 生产/Tauri 构建下 location.hostname 非 localhost，自动禁用（零生产影响）。
        const _isLocalDev =
          typeof window !== "undefined" &&
          (window.location.hostname === "127.0.0.1" ||
            window.location.hostname === "localhost");
        const devWs = _isLocalDev
          ? (localStorage.getItem('fnix.dev.workspace') || '').trim()
          : '';
        const initialPath = devWs || last;
        if (initialPath) {
          setProjectPath(initialPath);
          void setProjectRoot(initialPath).catch(() => {});
        }

        const hasKey = Boolean(
          nextConfig.api_key?.trim() ||
          nextProviders.some((p) => p.apiKey?.trim()) ||
          hasLocalLlmBootstrap(),
        );
        if (!isOnboardingDone() && !hasKey) {
          setShowOnboarding(true);
        }
      } catch (e) {
        // 启动序列个别步骤失败不应让 UI 卡在加载态：记录错误，仍用默认配置完成启动
        console.error('[boot] startup sequence partially failed, falling back to defaults', e);
      } finally {
        setBooted(true);
      }
    })();
  }, []);

  // Code 出现待确认变更 → 自动展开评审 tab（同一批变更只触发一次，用户关闭后不反复打扰）
  const reviewAutoSig = `${pendingChanges.length}:${pendingChanges.map((c) => c.path).join('|')}`;
  useEffect(() => {
    if (!canOpenReview({ mode, hasPending: pendingChanges.length > 0 })) return;
    if (reviewAutoSigRef.current === reviewAutoSig) return;
    reviewAutoSigRef.current = reviewAutoSig;
    if (panelTouchedRef.current) return;
    setInspectorTab('review');
    if (!reviewPath || !pendingChanges.some((c) => c.path === reviewPath)) {
      setReviewPath(pendingChanges[0]?.path ?? null);
    }
  }, [mode, pendingChanges, reviewAutoSig, reviewPath, setInspectorTab, setReviewPath]);

  // Deliver 首个产物落盘 → 自动展开结果 tab（每轮一次；用户手动操作过面板则不打扰）
  useEffect(() => {
    const n = chat.artifacts.length;
    const was = prevArtCountRef.current;
    prevArtCountRef.current = n;
    if (was === 0 && n > 0 && isDeliver && !panelTouchedRef.current) {
      setInspectorTab('results');
    }
  }, [chat.artifacts.length, isDeliver, setInspectorTab]);

  useEffect(() => {
    const tick = () => {
      // While a run is streaming, keep Ready sticky — a slow /health must not
      // flip the whole shell Offline and scare users mid-task.
      if (chat.streaming) {
        // BUG-021 fix: skip state update if value unchanged to avoid re-render
        if (useWorkspaceStore.getState().agentdOk !== true) setAgentdOk(true);
        return;
      }
      void pingAgentd({ timeoutMs: 4000 }).then((ok) => {
        // BUG-021 fix: only trigger re-render when status actually changes
        if (useWorkspaceStore.getState().agentdOk !== ok) setAgentdOk(ok);
      });
    };
    tick();
    const id = window.setInterval(tick, 12_000);
    return () => window.clearInterval(id);
  }, [chat.streaming, setAgentdOk]);

  useEffect(() => {
    setDraft('');
  }, [mode, chat.activeId]);

  useEffect(() => {
    const label = projectPath
      ? projectDisplayName(
          recentProjects.find((p) => p.path === projectPath) || { path: projectPath },
        )
      : '';
    const title = mode === 'code' ? (projectPath ? `Fnix Code —${label}` : 'Fnix Code') : 'Fnix';
    void setDesktopWindowTitle(title);
    document.title = title;
  }, [mode, projectPath, recentProjects]);

  const openProject = useCallback(
    async (path: string, opts?: { goHome?: boolean }) => {
      upsertRecent(path);
      if (opts?.goHome !== false) setPane('project');
      try {
        await setProjectRoot(path);
        await saveRecentProjectPath(path);
        await addRecentProject(path);
      } catch {
        /* browser / no tauri —still use agentd ensure */
      }
      void ensureFnixWorkspace(path);
      void indexHarnessWorkspace(path);
    },
    [setPane, upsertRecent],
  );

  const pickFolder = useCallback(async (): Promise<string | null> => {
    try {
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected === 'string' && selected) {
        await openProject(selected);
        return selected;
      }
    } catch {
      chat.setError(
        IS_DESKTOP
          ? '无法打开文件夹选择器，请重试或检查系统权限。'
          : '请用桌面端打开（pnpm tauri:dev），浏览器里无法选择本机文件夹。',
      );
    }
    return null;
  }, [chat, openProject]);

  const MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024; // 10MB
  const ALLOWED_IMAGE_TYPES = [
    'image/png',
    'image/jpeg',
    'image/gif',
    'image/webp',
    'image/svg+xml',
  ];

  const handlePickFiles = useCallback(
    (files: FileList) => {
      for (const file of Array.from(files)) {
        if (file.size > MAX_ATTACHMENT_SIZE) {
          chat.setError(`⚠️ 文件「${file.name}」过大（上限 10MB）。`);
          continue;
        }
        const isImage = ALLOWED_IMAGE_TYPES.includes(file.type);
        const reader = new FileReader();
        reader.onload = () => {
          const base64 = (reader.result as string).split(',')[1] ?? '';
          const att: ChatAttachment = {
            id: `att-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            name: file.name,
            type: isImage ? 'image' : 'file',
            mimeType: file.type || 'application/octet-stream',
            base64,
            size: file.size,
          };
          setAttachments((prev) => [...prev, att]);
        };
        reader.readAsDataURL(file);
      }
    },
    [chat],
  );

  const removeAttachment = useCallback((id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  }, []);

  const startNewChat = useCallback(() => {
    chat.newChat();
    setPane('home');
    setDraft('');
  }, [chat]);

  const sendDraft = () => {
    const t = draft.trim();
    if (!t && attachments.length === 0) return;
    if (mode === 'code' && !projectPath) {
      // 无仓库时不静默失败：保留草稿 + 内联提示（不打断输入流）
      setRepoHint(true);
      return;
    }
    setRepoHint(false);
    setDraft('');
    if (isBenchmarkPrompt(t)) {
      setAttachments([]);
      setShowBenchmark(true);
      setPane('home');
      return;
    }
    setPane('home');
    void chat.send(t, attachments);
    setAttachments([]);
  };

  useShellHotkeys({
    // BUG-6 fix: Work 模式被路由到 Code 管线时也需要快捷键
    enabled: mode === 'code' || pendingChanges.length > 0,
    reviewOpen: inspectorOpen && inspectorTab === 'review',
    canAccept:
      pendingChanges.length > 0 &&
      chat.applyStatus !== 'applying' &&
      chat.applyStatus !== 'undoing' &&
      !chat.streaming,
    canAcceptFile:
      Boolean(reviewPath) &&
      pendingChanges.length > 0 &&
      chat.applyStatus !== 'applying' &&
      chat.applyStatus !== 'undoing' &&
      !chat.streaming,
    canUndo:
      Boolean(chat.lastChangesetId) &&
      chat.applyStatus !== 'applying' &&
      chat.applyStatus !== 'undoing' &&
      !chat.streaming,
    onCloseReview: closeInspector,
    onAcceptAll: () => void chat.applyFileChanges(),
    onAcceptFile: () => {
      if (reviewPath) void chat.applyFileChanges([reviewPath]);
    },
    onUndo: () => void chat.undoLastApply(),
    onSkipToMain: () => {
      document.getElementById('fnix-main')?.focus();
    },
  });

  return (
    <div
      className={`fnix-root fnix-glass theme-${themeResolved}${IS_DESKTOP ? ' is-desktop' : ' is-web-preview'}${asideOpen ? '' : ' aside-collapsed'}`}
      data-theme={themeResolved}
      data-mode={mode}
    >
      <a href="#fnix-main" className="fnix-skip-link">
        跳到主内容
      </a>
      {!IS_DESKTOP && !hintDismissed && (
        <div className="fnix-desktop-hint">
          <span>
            当前是浏览器预览。产品形态是 <b>Tauri 桌面端</b> — 请运行{' '}
            <code>pnpm --filter @fnixagent/workbench tauri:dev</code> 以使用打开文件夹等能力。
          </span>
          <button
            type="button"
            className="fnix-desktop-hint-x"
            aria-label="关闭提示"
            onClick={() => {
              setHintDismissed(true);
              try {
                localStorage.setItem('fnix.web-hint-dismissed', '1');
              } catch {
                /* ignore */
              }
            }}
          >
            <X size={13} />
          </button>
        </div>
      )}
      <aside className="fnix-side" data-tauri-drag-region={IS_DESKTOP ? true : undefined}>
        {/* Work | Code 左右分段（唯一产品开关）+ 收起侧栏 */}
        <div className="fnix-side-top">
          <ProductSegment value={mode} onChange={onProductChange} disabled={chat.streaming} />
          <button
            type="button"
            className="fnix-ibtn sm fnix-side-collapse"
            title="收起侧栏 (Ctrl+B)"
            aria-label="收起侧栏"
            onClick={() => setAsideOpen(false)}
          >
            <PanelLeftClose size={15} />
          </button>
        </div>

        <div className="fnix-nav">
          <button type="button" className="fnix-nav-primary" onClick={startNewChat}>
            <Plus size={16} />
            新任务
          </button>
        </div>

        <ThreadSidebar
          threads={allThreads}
          activeId={chat.activeId}
          hasSession={hasSession}
          streaming={chat.streaming}
          onOpen={(id) => {
            if (mode === 'work') void openWorkThread(id);
            else {
              setPane('home');
              void chat.openThread(id);
            }
          }}
          onRename={(id, title) => void chat.renameThread(id, title)}
          onDelete={(id) => void chat.deleteThread(id)}
        />

      </aside>

      {/* 全页面左下角固定设置/诊断 */}
      <div className="fnix-global-foot">
        <button
          type="button"
          className="fnix-global-settings"
          onClick={() => openSettings('models')}
          title="设置"
          aria-label="设置"
        >
          <SettingsIcon size={16} />
        </button>
        <button
          type="button"
          className="fnix-global-settings"
          onClick={() => setShowBenchmark(true)}
          title="诊断"
          aria-label="诊断"
        >
          <Activity size={15} />
        </button>
      </div>

      {/* 侧栏收起后：首页等无 ChatHead 的场景提供悬浮展开入口（会话内用 ChatHead 按钮） */}
      {!asideOpen && !hasSession ? (
        <button
          type="button"
          className="fnix-side-expand"
          title="展开侧栏 (Ctrl+B)"
          aria-label="展开侧栏"
          onClick={() => setAsideOpen(true)}
        >
          <PanelLeftOpen size={16} />
        </button>
      ) : null}

      <main id="fnix-main" className="fnix-main" tabIndex={-1}>
        {booted && !hasByok && (
          <div className="fnix-banner">
            <span>配置自己的 API Key（BYOK）后即可对话</span>
            <button type="button" onClick={() => openSettings('models')}>
              打开设置
            </button>
          </div>
        )}
        {chat.error && (
          <div className="fnix-banner" role="alert">
            <span>{chat.error}</span>
            <button type="button" onClick={() => void chat.regenerate()} disabled={chat.streaming}>
              重试
            </button>
            <button type="button" onClick={() => openSettings('models')}>
              打开设置
            </button>
            <button type="button" className="fnix-banner-x" onClick={() => chat.setError(null)}>
              ×
            </button>
          </div>
        )}

        {/* ── Projects library ── */}
        {pane === 'projects' && !hasSession && (
          <ProjectsLibrary
            projects={recentProjects}
            onOpenFolder={() => void pickFolder()}
            onSelect={(path) => void openProject(path)}
            onRename={(path, alias) => void renameProjectAlias(path, alias)}
          />
        )}

        {/* ── Project home ── */}
        {pane === 'project' && projectPath && !hasSession && (
          <ProjectHome
            path={projectPath}
            displayName={projectDisplayName(
              recentProjects.find((p) => p.path === projectPath) || { path: projectPath },
            )}
            threads={chat.threads}
            activeId={chat.activeId}
            onNewChat={startNewChat}
            onOpenThread={(id) => {
              setPane('home');
              void chat.openThread(id);
            }}
            onChangeFolder={() => void pickFolder()}
            onOpenCode={() => {
              setMode('code');
              setPane('home');
            }}
            onRename={(alias) => void renameProjectAlias(projectPath, alias)}
          />
        )}

        {/* ── Work home — 上品牌 / 下输入框 ── */}
        {mode === 'work' && pane === 'home' && !hasSession && (
          <div className="fnix-chat-home wb-home">
            <div className="fnix-home-hero">
              <div className="fnix-home-brand" aria-hidden>
                <span className="fnix-home-logo" />
                <span className="fnix-home-name">Fnix</span>
              </div>
              <h1>有什么可以帮你？</h1>
              <p className="fnix-chat-home-sub">
                {workMode === 'ask' ? '随意提问 — 不会写入文件' : '规划并交付文档、网站与分析'}
              </p>
            </div>
            <div className="fnix-home-dock">
              <Composer
                value={draft}
                onChange={setDraft}
                onSend={sendDraft}
                onStop={chat.stop}
                streaming={chat.streaming}
                placeholder={workModePlaceholder(workMode)}
                modelSlot={modelControl}
                leftExtraSlot={workModeControl}
                onPickFolder={() => void pickFolder()}
                onPickFiles={handlePickFiles}
                attachments={attachments}
                onRemoveAttachment={removeAttachment}
                projectPath={projectPath}
                projectLabel={projectLabel}
                autoFocus
              />
            </div>
          </div>
        )}

        {/* ── Work session：对话+ Results ── */}
        {mode === 'work' && hasSession && (
          <section className={`fnix-chat-full${inspectorOpen ? ' fnix-work-split' : ''}`}>
            <div className="fnix-work-main">
              <ChatHead
                onToggleAside={() => setAsideOpen((v) => !v)}
                onNewChat={startNewChat}
                skillsOpen={skillsOpen}
                onToggleSkills={() => {
                  setSkillsOpen((v) => !v);
                  if (!skillsOpen) setJobsOpen(false);
                }}
                inspectorOpen={inspectorOpen}
                onToggleInspector={toggleInspectorUser}
                jobsOpen={jobsOpen}
                activeJobCount={activeJobCount}
                onToggleJobs={() => {
                  setJobsOpen((v) => !v);
                  if (!jobsOpen) setSkillsOpen(false);
                }}
                projectPath={projectPath}
                projectLabel={projectLabel}
                onOpenProject={() => setPane('project')}
              />

              <MessageList
                messages={chat.messages}
                streaming={chat.streaming}
                status={chat.status}
                onRegenerate={() => void chat.regenerate()}
                fileChanges={chat.fileChanges}
                onPin={pinArtifact}
                onSendPrompt={(t) => void chat.send(t)}
              />
              <ProcessTimeline
                key={`${chat.activeId}-${chat.goalStartedAt || 0}`}
                items={chat.activities}
                streaming={chat.streaming}
                onStop={chat.stop}
                compact
              />
              <div className="fnix-chat-dock">
                <Composer
                  value={draft}
                  onChange={setDraft}
                  onSend={sendDraft}
                  onStop={chat.stop}
                  streaming={chat.streaming}
                  placeholder={workModePlaceholder(workMode)}
                  modelSlot={modelControl}
                  leftExtraSlot={workModeControl}
                  onPickFolder={() => void pickFolder()}
                  onPickFiles={handlePickFiles}
                  attachments={attachments}
                  onRemoveAttachment={removeAttachment}
                  projectPath={projectPath}
                  projectLabel={projectLabel}
                  compact
                />
                {/* 进化辅助信息（KTG/STP/MFP）与 Craft 写入提示已移至设置 → Diagnostics「进化内核」卡片，主界面保持简洁 */}
              </div>
            </div>
            {inspectorOpen ? (
              <StudioPanel
                tabs={workTabs}
                tab={effectiveTab}
                onTabChange={setInspectorTab}
                onClose={closeInspector}
                views={{
                  canvas: (
                    <CanvasView
                      workspace={projectPath}
                      apiBase={getFnixApiBase()}
                      fileChanges={chat.fileChanges}
                    />
                  ),
                  // BUG-6 fix: Work 模式被路由到 Code 管线时，review tab 需要渲染 ReviewView
                  review: pendingChanges.length > 0 ? (
                    <ReviewView
                      changes={pendingChanges}
                      codeBlocks={codeBlocks}
                      applyStatus={chat.applyStatus}
                      applyMessage={chat.applyMessage}
                      streaming={chat.streaming}
                      lastChangesetId={chat.lastChangesetId}
                      activePath={reviewPath}
                      onSelectPath={setReviewPath}
                      onReject={() =>
                        chat.clearFileChanges('已拒绝所有变更，可在下轮对话重新生成。')
                      }
                      onAccept={() => void chat.applyFileChanges()}
                      onAcceptFile={(path) => void chat.applyFileChanges([path])}
                      onAcceptPartial={(change) => void chat.applyPartialFileChange(change)}
                      onUndo={() => void chat.undoLastApply()}
                    />
                  ) : undefined,
                  results: isDeliver ? (
                    <ResultsView
                      artifacts={chat.artifacts}
                      mission={chat.mission}
                      workMode={workMode}
                      workspace={projectPath}
                      streaming={chat.streaming}
                      canExecutePlan={
                        workMode === 'plan' &&
                        chat.messages.some((m) => m.role === 'assistant' && m.content.trim())
                      }
                      onExecutePlan={executePlan}
                    />
                  ) : undefined,
                  terminal: (
                    <TerminalView activities={chat.activities} streaming={chat.streaming} />
                  ),
                  browser: <BrowserView artifacts={chat.artifacts} apiBase={getFnixApiBase()} />,
                }}
              />
            ) : null}
          </section>
        )}

        {/* ── Code home — 与 Work 同构：上品牌 / 下 Composer ── */}
        {mode === 'code' && pane === 'home' && !hasSession && (
          <div className="fnix-chat-home wb-home">
            <div className="fnix-home-hero">
              <div className="fnix-home-brand" aria-hidden>
                <span className="fnix-home-logo code" />
                <span className="fnix-home-name">Fnix Code</span>
              </div>
              <h1>有什么可以帮你？</h1>
              <p className="fnix-chat-home-sub">
                {projectPath ? `仓库 · ${projectLabel}` : '先打开一个仓库，然后描述要修改的内容'}
              </p>
              {projectPath ? null : (
                <button type="button" className="fnix-primary" onClick={() => void pickFolder()}>
                  <FolderOpen size={15} />
                  打开仓库
                </button>
              )}
            </div>
            <div className="fnix-home-dock">
              <Composer
                value={draft}
                onChange={setDraft}
                onSend={sendDraft}
                onStop={chat.stop}
                streaming={chat.streaming}
                placeholder="描述要做的代码修改…"
                  modelSlot={modelControl}
                  onPickFolder={() => void pickFolder()}
                  onPickFiles={handlePickFiles}
                  attachments={attachments}
                  onRemoveAttachment={removeAttachment}
                  projectPath={projectPath}
                  projectLabel={projectLabel}
                  sendDisabled={mode === 'code' && !projectPath}
                  compact
                />
              {!projectPath && (repoHint || draft.trim()) ? (
                <div className="fnix-inline-hint" role="status">
                  请先在左侧打开一个仓库，再发送代码修改任务
                </div>
              ) : null}
            </div>
          </div>
        )}

        {/* ── Code session：与 Work 同构 + Review 侧栏 ── */}
        {mode === 'code' && hasSession && (
          <section className={`fnix-chat-full${inspectorOpen ? ' fnix-work-split' : ''}`}>
            <div className="fnix-work-main">
              <ChatHead
                onToggleAside={() => setAsideOpen((v) => !v)}
                onNewChat={startNewChat}
                skillsOpen={skillsOpen}
                onToggleSkills={() => {
                  setSkillsOpen((v) => !v);
                  if (!skillsOpen) setJobsOpen(false);
                }}
                inspectorOpen={inspectorOpen}
                onToggleInspector={toggleInspectorUser}
                inspectorBadge={pendingChanges.length || undefined}
                inspectorDot={pendingChanges.length > 0 ? reviewRisk.maxLevel : undefined}
                projectPath={projectPath}
                projectLabel={projectLabel}
                onOpenProject={() => setPane('project')}
              />
              <MessageList
                messages={chat.messages}
                streaming={chat.streaming}
                status={chat.status}
                onRegenerate={() => void chat.regenerate()}
                fileChanges={pendingChanges}
                onOpenDiff={(path) => {
                  setInspectorTab('review');
                  setReviewPath(path);
                }}
                onPin={pinArtifact}
                onSendPrompt={(t) => void chat.send(t)}
              />
              <ProcessTimeline
                key={`${chat.activeId}-${chat.goalStartedAt || 0}`}
                items={chat.activities}
                streaming={chat.streaming}
                onStop={chat.stop}
                compact
                onOpenDiff={(path) => {
                  setInspectorTab('review');
                  setReviewPath(path);
                }}
              />
              <div className="fnix-chat-dock">
                <Composer
                  value={draft}
                  onChange={setDraft}
                  onSend={sendDraft}
                  onStop={chat.stop}
                  streaming={chat.streaming}
                  placeholder="描述要做的代码修改…"
                modelSlot={modelControl}
                onPickFolder={() => void pickFolder()}
                onPickFiles={handlePickFiles}
                attachments={attachments}
                onRemoveAttachment={removeAttachment}
                projectPath={projectPath}
                projectLabel={projectLabel}
                sendDisabled={mode === 'code' && !projectPath}
                autoFocus
              />
                <p className="fnix-disclaimer">Code · 预览 → 确认写盘</p>
              </div>
            </div>
            {inspectorOpen ? (
              <StudioPanel
                tabs={codeTabs}
                tab={effectiveTab}
                onTabChange={setInspectorTab}
                onClose={closeInspector}
                views={{
                  canvas: (
                    <CanvasView
                      workspace={projectPath}
                      apiBase={getFnixApiBase()}
                      fileChanges={pendingChanges}
                    />
                  ),
                  review: (
                    <ReviewView
                      changes={pendingChanges}
                      codeBlocks={codeBlocks}
                      applyStatus={chat.applyStatus}
                      applyMessage={chat.applyMessage}
                      streaming={chat.streaming}
                      lastChangesetId={chat.lastChangesetId}
                      activePath={reviewPath}
                      onSelectPath={setReviewPath}
                      onReject={() =>
                        chat.clearFileChanges('已拒绝所有变更，可在下轮对话重新生成。')
                      }
                      onAccept={() => void chat.applyFileChanges()}
                      onAcceptFile={(path) => void chat.applyFileChanges([path])}
                      onAcceptPartial={(change) => void chat.applyPartialFileChange(change)}
                      onUndo={() => void chat.undoLastApply()}
                    />
                  ),
                  terminal: (
                    <TerminalView activities={chat.activities} streaming={chat.streaming} />
                  ),
                  browser: <BrowserView artifacts={chat.artifacts} apiBase={getFnixApiBase()} />,
                }}
              />
            ) : null}
          </section>
        )}
        <FnixStatusBar
          agentdOk={agentdOk}
          llmProvider={config.provider}
          llmModel={config.model}
          hasApiKey={hasByok}
          projectPath={projectPath}
          apiBase={getFnixApiBase()}
        />
        {/* R6: 右栏关闭后恢复入口 — 仅无 ChatHead 场景（会话内用 ChatHead inspector 按钮） */}
        {!inspectorOpen && !hasSession ? (
          <button
            type="button"
            className="fnx-studio-expand"
            title="展开工作台面 (Ctrl+\)"
            aria-label="展开工作台面"
            onClick={() => setInspectorOpen(true)}
          >
            <PanelRight size={16} />
          </button>
        ) : null}
        {jobsOpen ? <TaskBoard workspace={projectPath} onClose={() => setJobsOpen(false)} /> : null}
        {skillsOpen ? (
          <SkillManager workspace={projectPath} onClose={() => setSkillsOpen(false)} />
        ) : null}
      </main>

      {showOnboarding && (
        <OnboardingWizard
          initialKey={config.api_key || LOCAL_LLM.apiKey || ''}
          initialModel={config.model || LOCAL_LLM.model}
          initialBaseUrl={LOCAL_LLM.baseUrl}
          projectPath={projectPath}
          onPickFolder={pickFolder}
          onSkip={() => {
            markOnboardingDone();
            setShowOnboarding(false);
          }}
          onComplete={async (result) => {
            const nextConfig: AppConfig = {
              ...config,
              provider: LOCAL_LLM.provider,
              model: result.model,
              api_key: result.apiKey,
            };
            const nextProviders = [
              {
                id: 'local-dashscope',
                type: 'openai-compatible' as const,
                name: LOCAL_LLM.providerName,
                apiKey: result.apiKey,
                baseUrl: result.baseUrl,
                models: [{ id: result.model, name: result.model, enabled: true }],
              },
            ];
            setConfig(nextConfig);
            setProviders(nextProviders);
            await saveAIProviders(nextProviders).catch(() => undefined);
            await saveConfigToStore(nextConfig).catch(() => undefined);
            await syncHarnessConfig({
              provider: LOCAL_LLM.provider,
              model: result.model,
              base_url: result.baseUrl,
              api_key: result.apiKey,
            });
            // BUG-022 fix: sync LOCAL_LLM after onboarding save
            updateLocalLlm({
              apiKey: result.apiKey,
              model: result.model,
              baseUrl: result.baseUrl,
            });
            if (result.projectPath) {
              await openProject(result.projectPath, { goHome: true });
            }
            setShowOnboarding(false);
          }}
        />
      )}

      {showBenchmark && (
        <FullChainBenchmarkPanel
          workspace={projectPath || undefined}
          onClose={() => setShowBenchmark(false)}
        />
      )}

      {showSettings && (
        <DesktopSettings
          config={config}
          providers={providers}
          initialSection={settingsSection}
          onConfigChange={setConfig}
          onProvidersChange={setProviders}
          onClose={() => setShowSettings(false)}
          onOpenBenchmark={() => {
            setShowSettings(false);
            setShowBenchmark(true);
          }}
          projectPath={projectPath}
        />
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        threads={chat.threads}
        mode={mode}
        onOpenThread={(id) => {
          if (mode === 'work') void openWorkThread(id);
          else {
            setPane('home');
            void chat.openThread(id);
          }
        }}
        onNewChat={startNewChat}
        onOpenSettings={() => openSettings('models')}
        onToggleMode={() => onProductChange(mode === 'work' ? 'code' : 'work')}
        onOpenBenchmark={() => setShowBenchmark(true)}
        onOpenFolder={() => void pickFolder()}
      />

      <ShortcutCheatsheet open={keysOpen} onClose={() => setKeysOpen(false)} />
    </div>
  );
}
