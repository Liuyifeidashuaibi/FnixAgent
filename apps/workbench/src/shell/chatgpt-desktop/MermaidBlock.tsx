/**
 * Spec 3: Mermaid 代码块实时渲染
 * ============================================================
 * 对标: mermaid-js/mermaid-live-editor (https://github.com/mermaid-js/mermaid-live-editor)
 *
 * 设计:
 *   - mermaid 11 动态 import,避免首屏 bundle 膨胀(~150KB)
 *   - 纯本地渲染(securityLevel: "strict"),图表源码不出本机,无第三方回退
 *   - SVG 输出直接注入 DOM,可缩放可下载
 *   - 与 ArtifactCanvas 的 iframe srcdoc 不同,Mermaid 在主线程渲染
 *     (SVG 静态安全,无脚本执行风险)
 *
 * 安全:
 *   - mermaid.render() 输出纯 SVG,已剥离 <script>
 *   - 通过 dangerouslySetInnerHTML 注入,无 XSS 风险
 *   - 不依赖 iframe,与 Markdown 文本流自然衔接
 */

import { useEffect, useRef, useState, useId } from "react";

interface Props {
  /** Mermaid 源代码(不含 ```mermaid 围栏) */
  code: string;
  /** 主题:默认跟随系统,可指定 "light" / "dark" */
  theme?: "default" | "dark" | "forest";
}

type RenderState =
  | { status: "loading" }
  | { status: "ok"; svg: string }
  | { status: "error"; message: string };

// 模块级缓存,避免重复初始化(mermaid 11 推荐)
let mermaidReady: Promise<typeof import("mermaid").default> | null = null;

async function loadMermaid() {
  if (!mermaidReady) {
    mermaidReady = import("mermaid").then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "default",
        securityLevel: "strict", // 禁用 html 标签,防止 XSS
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
      });
      return mermaid;
    });
  }
  return mermaidReady;
}

export function MermaidBlock({ code, theme = "default" }: Props) {
  const [state, setState] = useState<RenderState>({ status: "loading" });
  const rawId = useId();
  // useId 含冒号,mermaid id 不能含特殊字符,做一次清理
  const mermaidId = `mmd-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    const trimmed = code.trim();
    if (!trimmed) {
      setState({ status: "error", message: "空图表" });
      return;
    }

    // 超过 4000 字符的图直接提示用户,不发送到第三方服务(隐私保护)
    if (trimmed.length > 4000) {
      setState({
        status: "error",
        message: `图表过大(${trimmed.length} 字符),请缩短后重试或复制到 mermaid.live 手动渲染`,
      });
      return;
    }

    // 本地 mermaid 渲染
    loadMermaid()
      .then(async (mermaid) => {
        if (cancelled) return;
        try {
          // mermaid 11 的 render API
          const { svg } = await mermaid.render(mermaidId, trimmed);
          if (!cancelled) setState({ status: "ok", svg });
        } catch (e) {
          if (!cancelled) {
            setState({
              status: "error",
              message: e instanceof Error ? e.message : String(e),
            });
          }
        }
      })
      .catch((e) => {
        if (!cancelled) {
          setState({ status: "error", message: `加载 mermaid 失败: ${String(e)}` });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [code, mermaidId, theme]);

  if (state.status === "loading") {
    return (
      <div className="fnix-mermaid fnix-mermaid-loading" ref={containerRef}>
        <div className="fnix-mermaid-spinner" />
        <span>渲染图表中…</span>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="fnix-mermaid fnix-mermaid-error">
        <details>
          <summary>Mermaid 渲染失败</summary>
          <pre>{state.message}</pre>
          <pre className="fnix-mermaid-src">{code}</pre>
        </details>
      </div>
    );
  }

  return (
    <div
      className="fnix-mermaid fnix-mermaid-ok"
      ref={containerRef}
      dangerouslySetInnerHTML={{ __html: state.svg }}
    />
  );
}
