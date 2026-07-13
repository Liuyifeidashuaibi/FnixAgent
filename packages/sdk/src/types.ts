/**
 * fnixagent API 类型定义
 * Phase 1.2 将通过 openapi-typescript 从后端 OpenAPI schema 自动生成
 */

export interface HealthResponse {
  status: 'ok';
  version: string;
}

export interface User {
  id: number;
  username: string;
  email: string;
  role: 'user' | 'admin';
  profile: Record<string, unknown>;
  quota_total: number;
  quota_used: number;
  created_at: string;
}

export interface LoginRequest {
  username: string;
  password_cipher: string; // RSA 加密后的密文(Phase 1.7)
  device_fingerprint?: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
  expires_in: number;
}

export interface Document {
  id: number;
  name: string;
  doc_type: string;
  source: string;
  size_bytes: number;
  created_at: string;
  user_id: number;
  metadata: Record<string, unknown>;
}

export interface Task {
  id: number;
  session_id: number;
  intent: string;
  reasoning_mode: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string;
}

// ===========================================================================
// AgentOS 类型 (/api/v1/agentos/*)
// ===========================================================================

/**
 * AgentOS 通用响应(对接 /api/v1/agentos/* 路由)。
 * 与 BaseResponse 风格一致,但允许端点直返字段,故保留索引签名。
 */
export interface AgentOSResponse<T = unknown> {
  success: boolean;
  message?: string;
  data?: T;
  [key: string]: unknown;
}

/** spawn 进程入参 */
export interface AgentOSSpawnInput {
  name: string;
  priority?: number;
  capabilities?: string[];
  parent_pid?: string;
}

/** kill 进程入参 */
export interface AgentOSKillInput {
  pid: string;
  reason?: string;
}

/** exec 系统调用入参 */
export interface AgentOSExecInput {
  syscall: string;
  args?: Record<string, unknown>;
  pid?: string;
}

/** llm 推理入参 */
export interface AgentOSLLMInput {
  prompt: string;
  pid?: string;
  system?: string;
}

/** 文件写入入参 */
export interface AgentOSFsWriteInput {
  path: string;
  content: string;
}

/** 记忆召回入参 */
export interface AgentOSMemRecallInput {
  query: string;
  layers?: string[];
  top_k?: number;
}

/** 记忆存储入参 */
export interface AgentOSMemStoreInput {
  content: string;
  layer?: string;
}

/** 记忆搜索入参 */
export interface AgentOSMemSearchInput {
  query: string;
  layer?: string;
  top_k?: number;
}

/** 工具调用入参 */
export interface AgentOSToolInvokeInput {
  tool_name: string;
  args?: Record<string, unknown>;
}

/** A2A 单播入参 */
export interface AgentOSA2ASendInput {
  target: string;
  content: string;
  type?: string;
}

/** 技能运行入参 */
export interface AgentOSSkillRunInput {
  name: string;
  args?: Record<string, unknown>;
}

/** 策略新增入参 */
export interface AgentOSPolicyAddInput {
  action: string;
  effect: string;
  subject?: string;
  priority?: number;
}

/** 审计查询入参 */
export interface AgentOSAuditInput {
  limit?: number;
  action?: string;
}

// ===========================================================================
// Coding 类型 (/api/v1/coding/*)
// ===========================================================================

/**
 * Coding 通用响应(对接 /api/v1/coding/* 路由)。
 * 与 AgentOSResponse 同构,语义化命名以区分模块。
 */
export interface CodingResponse<T = unknown> {
  success: boolean;
  message?: string;
  data?: T;
  [key: string]: unknown;
}

/** 代码索引入参 */
export interface CodingIndexInput {
  path?: string;
  no_incremental?: boolean;
}

/** 代码搜索入参 */
export interface CodingSearchInput {
  query: string;
  top_k?: number;
}

/** 文件读取入参 */
export interface CodingReadInput {
  file: string;
  start?: number;
  end?: number;
}

/** 文件写入入参 */
export interface CodingWriteInput {
  file: string;
  content: string;
}

/** 文件编辑入参(字符串替换) */
export interface CodingEditInput {
  file: string;
  old: string;
  new: string;
}

/** 自主编码任务入参 */
export interface CodingTaskInput {
  description: string;
  files?: string[];
  constraints?: Record<string, unknown>;
}

/** MCP 工具调用入参 */
export interface CodingMcpCallInput {
  tool: string;
  arguments: Record<string, unknown>;
}
