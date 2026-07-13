/**
 * OfficeAgent Studio — 核心类型定义
 *
 * 对标 Codex CLI + Cursor IDE,定义全局状态所需的所有类型。
 */

/** 工具调用记录 */
export interface ToolCallRecord {
  name: string;
  args?: Record<string, unknown>;
  result?: unknown;
  success?: boolean;
  /** 耗时(ms) */
  durationMs?: number;
}

/** Agent 运行状态 */
export type AgentStatus =
  | 'idle'
  | 'planning'
  | 'executing'
  | 'reviewing'
  | 'awaiting_user'
  | 'error';

/** 单条对话消息 */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  /** 流式标记:正在输出中 */
  streaming?: boolean;
  /** 工具调用列表(assistant 消息可附带) */
  toolCalls?: ToolCallRecord[];
  /** 概念路径(evolve 模式) */
  conceptPath?: string[];
  /** 耗时(ms) */
  durationMs?: number;
  /** 错误信息 */
  error?: string;
  /** 时间戳 */
  ts: number;
  /** 该消息产生时的 Agent 状态 */
  agentStatus?: AgentStatus;
}

/** 上下文 chip 类型 (@-mention) */
export type ContextChipType =
  | 'file'
  | 'folder'
  | 'codebase'
  | 'docs'
  | 'web'
  | 'terminal';

/** 上下文 chip */
export interface ContextChip {
  id: string;
  type: ContextChipType;
  value: string;
  label: string;
}

/** 文件变更状态 */
export type FileChangeStatus = 'pending' | 'accepted' | 'rejected';

/** 单个文件变更(待确认的代码变更) */
export interface FileChange {
  filePath: string;
  oldContent: string;
  newContent: string;
  addedLines: number;
  removedLines: number;
  status: FileChangeStatus;
}

/** Agent 进程信息 */
export interface AgentProcessInfo {
  pid: string;
  name: string;
  state: string;
  priority: number;
  tokensUsed: number;
  stepsExecuted: number;
  createdAt: number;
}

/** Composer 模式 */
export type ComposerMode = 'ask' | 'edit' | 'agent';

/** 应用模式:IDE 模式 / SOLO 模式 */
export type AppMode = 'ide' | 'solo';

/** 主题 */
export type Theme = 'light' | 'dark';

/** 左栏视图 */
export type LeftPanelView = 'files' | 'tasks' | 'processes' | 'search';

/** 右栏视图 */
export type RightPanelView = 'chat' | 'diff' | 'terminal' | 'memory' | 'policy';

/** 中栏视图(IDE=editor, SOLO=chat) */
export type CenterPanelView = 'editor' | 'chat';

/** 生成简单唯一 ID */
export function genId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}
