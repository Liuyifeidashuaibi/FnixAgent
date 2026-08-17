/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Local BYOK bootstrap for the ChatGPT shell (no model catalog).
 * Order: agentd env → public/local-llm.bootstrap.json → VITE_FNIX_*.
 */

import type { AIProviderConfig } from "../../utils/providers";
import type { AppConfig } from "../../utils/tauri";
import { loadLocalLlmBootstrap } from "../../lib/fnixBridge";

const env = (import.meta as ImportMeta & { env?: Record<string, string> }).env || {};

export type LocalLlm = {
  apiKey: string;
  model: string;
  baseUrl: string;
  provider: string;
  providerName: string;
};

export let LOCAL_LLM: LocalLlm = {
  apiKey: (env.VITE_FNIX_API_KEY || "").trim(),
  model: (env.VITE_FNIX_MODEL || "qwen-plus-2025-07-28").trim(),
  baseUrl: (
    env.VITE_FNIX_BASE_URL || "https://dashscope.aliyuncs.com/compatible-mode/v1"
  ).trim(),
  provider: (env.VITE_FNIX_PROVIDER || "qwen").trim(),
  providerName: (env.VITE_FNIX_PROVIDER_NAME || "DashScope (Qwen)").trim(),
};

function applyBoot(boot: {
  api_key?: string;
  apiKey?: string;
  model?: string;
  base_url?: string;
  baseUrl?: string;
  provider?: string;
  provider_name?: string;
  providerName?: string;
}) {
  const key = (boot.api_key || boot.apiKey || "").trim();
  if (!key) return false;
  LOCAL_LLM = {
    apiKey: key,
    model: (boot.model || LOCAL_LLM.model).trim(),
    baseUrl: (boot.base_url || boot.baseUrl || LOCAL_LLM.baseUrl).trim(),
    provider: (boot.provider || LOCAL_LLM.provider).trim(),
    providerName: (boot.provider_name || boot.providerName || LOCAL_LLM.providerName).trim(),
  };
  return true;
}

export function hasLocalLlmBootstrap(): boolean {
  return Boolean(LOCAL_LLM.apiKey);
}

async function loadPublicBootstrap(): Promise<boolean> {
  try {
    const res = await fetch(`/local-llm.bootstrap.json?t=${Date.now()}`, {
      cache: "no-store",
      signal: AbortSignal.timeout(2000),
    });
    if (!res.ok) return false;
    return applyBoot((await res.json()) as Record<string, string>);
  } catch {
    return false;
  }
}

/** Refresh LOCAL_LLM from agentd (.env) or public bootstrap file. */
export async function refreshLocalLlmFromAgentd(): Promise<boolean> {
  const fromAgentd = await loadLocalLlmBootstrap();
  if (fromAgentd && applyBoot(fromAgentd)) return true;
  if (await loadPublicBootstrap()) return true;
  return hasLocalLlmBootstrap();
}

export function localProviderConfig(): AIProviderConfig {
  return {
    id: "local-dashscope",
    type: "openai-compatible",
    name: LOCAL_LLM.providerName,
    apiKey: LOCAL_LLM.apiKey,
    baseUrl: LOCAL_LLM.baseUrl,
    models: [{ id: LOCAL_LLM.model, name: LOCAL_LLM.model, enabled: true }],
  };
}

export function localAppConfig(base: AppConfig): AppConfig {
  return {
    ...base,
    provider: LOCAL_LLM.provider,
    api_key: LOCAL_LLM.apiKey,
    model: LOCAL_LLM.model,
  };
}
