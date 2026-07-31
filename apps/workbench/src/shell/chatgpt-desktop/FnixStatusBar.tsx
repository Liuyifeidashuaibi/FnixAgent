/**
 * FnixStatusBar — 底部一行信号灯
 * 运行环境信号灯：agentd / LLM / workspace / sidecar
 * 极简新中式：白底 · 细灰顶边线 · 深灰文字 · 小圆点状态色
 */

import { useEffect, useState } from "react";
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

type SidecarState = "ok" | "down" | "checking";

interface HarnessStatus {
  sidecar?: { available?: boolean; url?: string; version?: string; runtime?: string };
  setup?: { has_provider?: boolean; has_model?: boolean; has_api_key?: boolean };
}

async function fetchHarnessStatus(apiBase: string): Promise<HarnessStatus | null> {
  try {
    const res = await fetch(`${apiBase}/api/v1/harness/status`, {
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return null;
    return (await res.json().catch(() => null)) as HarnessStatus | null;
  } catch {
    return null;
  }
}

export function FnixStatusBar({
  agentdOk,
  llmProvider,
  llmModel,
  hasApiKey,
  projectPath,
  apiBase,
}: Props) {
  const [harness, setHarness] = useState<HarnessStatus | null>(null);
  const [sidecar, setSidecar] = useState<SidecarState>("checking");

  useEffect(() => {
    let cancelled = false;
    const refresh = async () => {
      const st = await fetchHarnessStatus(apiBase);
      if (cancelled) return;
      setHarness(st);
      const avail = st?.sidecar?.available;
      if (typeof avail === "boolean") {
        setSidecar(avail ? "ok" : "down");
      } else {
        setSidecar("down");
      }
    };
    void refresh();
    const id = window.setInterval(refresh, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [apiBase]);

  // 1. agentd
  const agentdLight: Light = (() => {
    if (agentdOk === null) {
      return {
        color: "gray",
        label: "agentd 检测中",
        title: "agentd: 检测中…",
      };
    }
    if (agentdOk) {
      return { color: "green", label: "agentd 已就绪", title: "agentd: 已就绪" };
    }
    return {
      color: "red",
      label: "agentd 离线",
      title: `agentd: 离线 (${apiBase})`,
    };
  })();

  // 2. LLM
  const llmConfigured = Boolean(llmProvider && llmModel);
  const llmLabel = llmConfigured ? `${llmProvider} · ${llmModel}` : "LLM 未配置";
  const llmLight: Light = (() => {
    if (!llmConfigured) {
      return {
        color: "gray",
        label: llmLabel,
        title: "LLM: 未配置 provider/model",
      };
    }
    if (hasApiKey) {
      return {
        color: "green",
        label: llmLabel,
        title: `LLM: ${llmProvider} · ${llmModel} (key 已配置)`,
      };
    }
    return {
      color: "yellow",
      label: llmLabel,
      title: `LLM: ${llmProvider} · ${llmModel} (无 api_key)`,
    };
  })();

  // 3. workspace（A4 精简：仅在已选择时显示，避免无仓库灰点常驻噪音）
  const wsLight: Light | null = projectPath
    ? {
        color: "green",
        label: "workspace",
        title: `workspace: ${projectPath}`,
      }
    : null;

  // 4. sidecar
  const sidecarUrl = harness?.sidecar?.url || "http://127.0.0.1:8710";
  const sidecarLight: Light = (() => {
    if (sidecar === "checking") {
      return { color: "gray", label: "sidecar", title: "sidecar: 检测中…" };
    }
    if (sidecar === "ok") {
      return {
        color: "green",
        label: "sidecar",
        title: `sidecar: 已连接 (${sidecarUrl})`,
      };
    }
    return {
      color: "yellow",
      label: "sidecar",
      title: "sidecar: 不通（降级模式）",
    };
  })();

  const lights: Light[] = [agentdLight, llmLight, sidecarLight];
  if (wsLight) lights.splice(2, 0, wsLight);

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
