/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * FnixStatusBar — 底部一行信号灯
 * 运行环境信号灯：agentd / LLM / workspace / sidecar
 * 极简新中式：白底 · 细灰顶边线 · 深灰文字 · 小圆点状态色
 */

import { useState } from "react";
import "./FnixStatusBar.css";

interface Props {
  agentdOk: boolean | null;
  llmProvider: string;
  llmModel: string;
  hasApiKey: boolean;
  projectPath: string;
  apiBase: string;
}

type DotColor = "green" | "yellow" | "red" | "gray";

interface Light {
  color: DotColor;
  label: string;
  title: string;
}

export function FnixStatusBar({
  agentdOk,
  llmProvider,
  llmModel,
  hasApiKey,
  projectPath,
}: Props) {
  // 0. agentd — 后端连通性是执行任务的前提,离线时红色显式提示
  const agentdLight: Light = (() => {
    if (agentdOk === true) {
      return { color: "green", label: "agentd", title: "agentd: 已连接" };
    }
    if (agentdOk === false) {
      return { color: "red", label: "agentd 离线", title: "agentd: 后端未响应，任务将无法执行" };
    }
    return { color: "gray", label: "agentd", title: "agentd: 连接中…" };
  })();

  // 1. LLM — 用户需要知道当前用的什么模型；未配置时柔和引导
  const llmConfigured = Boolean(llmProvider && llmModel);
  const llmLabel = llmConfigured ? `${llmProvider} · ${llmModel}` : "LLM 未配置";
  const llmLight: Light | null = (() => {
    if (!llmConfigured) {
      return { color: "gray", label: llmLabel, title: "LLM: 未配置 provider/model" };
    }
    if (hasApiKey) {
      return { color: "green", label: llmLabel, title: `LLM: ${llmProvider} · ${llmModel} (key 已配置)` };
    }
    return { color: "yellow", label: llmLabel, title: `LLM: ${llmProvider} · ${llmModel} (无 api_key)` };
  })();

  // 3. workspace（仅在已选择时显示）
  const wsLight: Light | null = projectPath
    ? { color: "green", label: "workspace", title: `workspace: ${projectPath}` }
    : null;

  const lights: Light[] = [];
  lights.push(agentdLight);
  if (wsLight) lights.push(wsLight);
  if (llmLight) lights.push(llmLight);

  return (
    <div className="fnix-status-bar" role="status">
      {lights.map((l, i) => (
        <span key={i} className="fnix-status-light" title={l.title}>
          <span className={`fnix-status-dot ${l.color}`} />
          <span className="fnix-status-label">{l.label}</span>
        </span>
      ))}
    </div>
  );
}
