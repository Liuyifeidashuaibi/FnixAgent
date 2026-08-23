/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * anthropicTypes.ts — Anthropic Messages API types (Claude 4 compatible).
 *
 * Covers the full request/response and SSE streaming event contracts.
 * Reference: https://docs.anthropic.com/en/api/messages
 */

// ── Request Types ─────────────────────────────────────────────────────────────

export interface RequestMessage {
  role: "user" | "assistant";
  content: ContentBlock[] | string;
}

export type ContentBlock =
  | TextBlock
  | ImageBlock
  | ToolUseBlock
  | ToolResultBlock;

export interface TextBlock {
  type: "text";
  text: string;
}

export interface ImageBlock {
  type: "image";
  source: {
    type: "base64";
    media_type: string;
    data: string;
  };
}

export interface ToolUseBlock {
  type: "tool_use";
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolResultBlock {
  type: "tool_result";
  tool_use_id: string;
  content: string;
  is_error?: boolean;
}

export interface MessagesRequest {
  model: string;
  max_tokens: number;
  system?: string;
  messages: RequestMessage[];
  temperature?: number;
  stream?: boolean;
  tools?: ToolDefinition[];
}

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

// ── Response Types (non-streaming) ────────────────────────────────────────────

export interface MessagesResponse {
  id: string;
  type: "message";
  role: "assistant";
  content: ResponseBlock[];
  model: string;
  stop_reason: "end_turn" | "max_tokens" | "stop_sequence" | "tool_use";
  usage: Usage;
}

export type ResponseBlock =
  | { type: "text"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> };

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
}

// ── SSE Streaming Event Types ─────────────────────────────────────────────────

export type StreamEvent =
  | MessageStartEvent
  | ContentBlockStartEvent
  | ContentBlockDeltaEvent
  | ContentBlockStopEvent
  | MessageDeltaEvent
  | MessageStopEvent
  | PingEvent
  | ErrorEvent;

export interface MessageStartEvent {
  type: "message_start";
  message: {
    id: string;
    type: "message";
    role: "assistant";
    model: string;
    usage: { input_tokens: number; output_tokens: number };
  };
}

export interface ContentBlockStartEvent {
  type: "content_block_start";
  index: number;
  content_block: { type: "text"; text: string } | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> };
}

export interface ContentBlockDeltaEvent {
  type: "content_block_delta";
  index: number;
  delta: { type: "text_delta"; text: string } | { type: "input_json_delta"; partial_json: string };
}

export interface ContentBlockStopEvent {
  type: "content_block_stop";
  index: number;
}

export interface MessageDeltaEvent {
  type: "message_delta";
  delta: { stop_reason: string };
  usage: { output_tokens: number };
}

export interface MessageStopEvent {
  type: "message_stop";
}

export interface PingEvent {
  type: "ping";
}

export interface ErrorEvent {
  type: "error";
  error: { type: string; message: string };
}
