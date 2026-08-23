/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Anthropic Provider — Public API.
 *
 * Usage:
 *   import { sendTo, sendToStreaming } from "../providers/anthropic";
 */

export { sendTo, sendToStreaming } from "./AnthropicProvider";
export type { StreamCallbacks, StreamAccumulator } from "./anthropicStream";
export type {
  MessagesRequest,
  MessagesResponse,
  StreamEvent,
  Usage,
} from "./anthropicTypes";
