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

import './FnixStatusBar.css';

interface Props {
  agentdOk: boolean | null;
  llmProvider: string;
  llmModel: string;
  hasApiKey: boolean;
  projectPath: string;
  apiBase: string;
}

type DotColor = 'green' | 'yellow' | 'red' | 'gray';

interface Light {
  color: DotColor;
  label: string;
  title: string;
}

export function FnixStatusBar({ agentdOk, llmProvider, llmModel, hasApiKey }: Props) {
  // 仅在异常状态下显示信号灯，正常状态隐藏避免冗余
  // — 后端离线 → 红色警告（必须提示）
  // — 模型未配置 → 灰色提示
  // — 无 api_key → 黄色提示
  // — 一切正常 → 不显示（聊天框已有模型选择，workspace 已在侧栏）
  const lights: Light[] = [];

  if (agentdOk === false) {
    lights.push({ color: 'red', label: 'agentd 离线', title: 'agentd: 后端未响应，任务将无法执行' });
  } else if (agentdOk === null) {
    lights.push({ color: 'gray', label: 'agentd 连接中…', title: 'agentd: 连接中…' });
  }

  const llmConfigured = Boolean(llmProvider && llmModel);
  if (!llmConfigured) {
    lights.push({ color: 'gray', label: 'LLM 未配置', title: 'LLM: 未配置 provider/model' });
  } else if (!hasApiKey) {
    lights.push({
      color: 'yellow',
      label: `${llmProvider} · ${llmModel} (无 api_key)`,
      title: `LLM: ${llmProvider} · ${llmModel} (无 api_key)`,
    });
  }

  if (lights.length === 0) return null;

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
