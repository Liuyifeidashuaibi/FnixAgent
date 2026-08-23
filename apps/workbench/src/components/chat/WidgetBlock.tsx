/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * WidgetBlock — AI 内联可视化（动态 UI 渲染）
 * ============================================================
 *
 * 调研：
 * - 动态 UI 渲染：模型写 SVG/HTML，PureShowWidget 工具在对话流内渲染；
 *   window.sendPrompt 桥接「widget 按钮 → 回灌对话」
 * - Claude Inline Visualizations：Settings → Visuals 开关，HTML/SVG 即时渲染
 * - 内联产物 安全方案：iframe sandbox + 全站点进程隔离 + 严格 CSP
 *
 * 三层安全防御（借鉴 内联产物）：
 *   1. iframe sandbox="allow-scripts"（不加 allow-same-origin，防 sandbox 逃逸）
 *   2. 严格 CSP：default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
 *      img-src data: blob:; connect-src 'none'（禁止 fetch/XHR/WebSocket，防数据外传）
 *   3. 轻量 regex 清洗：移除 on* 内联事件处理器 + javascript: 协议
 *      （skill 契约要求交互用 addEventListener，<script> 仍可执行）
 *
 * postMessage 桥（sandbox 下唯一的 iframe↔宿主通道）：
 *   - fnix-widget-height：iframe 内 ResizeObserver 上报内容高度（sandbox 无
 *     allow-same-origin 时宿主读不到 contentDocument，必须由内部上报）
 *   - fnix-widget-prompt：widget 内 window.sendPrompt(text) → 宿主回灌为新用户消息
 *
 * 与 ArtifactCanvas 的边界：
 * - WidgetBlock = 过程数据（内存中的 chart spec / table data，一次性，不可编辑）
 * - ArtifactCanvas = 磁盘产物（文件，可编辑可持久化，AI patch 增量编辑）
 */

import { memo, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronRight, Maximize2 } from 'lucide-react';
import type { WidgetBlock as WidgetBlockData } from '../../utils/structuredBlocks';

interface Props {
  block: WidgetBlockData;
  /** 是否实时（流式） */
  live: boolean;
  /** 钉到画布回调（可选） */
  onPin?: (data: { widgetType: string; code: string }) => void;
  /** widget 内 sendPrompt 按钮 → 回灌对话（可选） */
  onSendPrompt?: (text: string) => void;
}

/**
 * 轻量 HTML 清洗 — 移除 on* 内联事件处理器 + javascript: 协议。
 *
 * 设计取舍：
 * - 不引入 DOMPurify（3KB 外部依赖），用 regex 即可覆盖主要 XSS 向量
 * - skill 契约（dynamic-ui SKILL.md）要求交互一律在 <script> 里 addEventListener，
 *   所以剥离内联 on*= 不影响合规 widget 的交互能力
 * - iframe sandbox="allow-scripts" 已阻止 JS 访问父窗口
 * - CSP connect-src 'none' 已阻止数据外传
 */
function sanitizeWidgetCode(code: string): string {
  return (
    code
      // 移除 on* 内联事件处理器（onerror / onload / onclick / onmouseover 等）
      .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
      // 移除 javascript: 协议
      .replace(/(href|src)\s*=\s*["']javascript:[^"']*["']/gi, '$1="#"')
      // 移除 data: 协议中的 script（data:text/html）
      .replace(/(href|src)\s*=\s*["']data:text\/html[^"']*["']/gi, '$1="#"')
  );
}

/**
 * 构造 iframe srcdoc — 注入 CSP + 主题 token + postMessage 桥。
 *
 * 主题 token 与 17-cline-chat-blocks.css 的过程可视化配色一致：
 * - 青灰 #4a6fa5（主色）
 * - 茶白 #f8f6f0（底色）
 * - 茶绿 #5a7a5a（成功）
 * - 赭石 #a85751（错误）
 * - 墨黄 #8a7848（等待）
 */
function buildSrcDoc(code: string, widgetId: string): string {
  const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none';">`;
  const theme = `<style>
  :root {
    --brand: #4a6fa5;
    --brand-soft: rgba(74, 111, 165, 0.08);
    --surface: #ffffff;
    --surface-muted: #f8f6f0;
    --text-primary: #1f2937;
    --text-secondary: #4b5563;
    --text-muted: #9ca3af;
    --border: #e5e7eb;
    --success: #5a7a5a;
    --danger: #a85751;
    --warning: #8a7848;
    --radius: 8px;
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    --font-mono: "SF Mono", "JetBrains Mono", Consolas, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --brand: #7c95c2;
      --brand-soft: rgba(124, 149, 194, 0.1);
      --surface: #1a1a1f;
      --surface-muted: #24242b;
      --text-primary: #f3f4f6;
      --text-secondary: #d1d5db;
      --text-muted: #8b8f99;
      --border: #34343d;
      --success: #7da87d;
      --danger: #c97a73;
      --warning: #b59970;
    }
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 12px;
    background: var(--surface);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: 14px;
    line-height: 1.5;
  }
</style>`;
  // 桥接脚本：高度上报 + sendPrompt（sandbox 无 allow-same-origin，
  // 宿主读不到 contentDocument，高度必须由 iframe 内部 postMessage 上报）
  const wid = JSON.stringify(widgetId);
  const bridge = `<script>
  (function () {
    var WID = ${wid};
    function report() {
      try {
        var h = document.body ? document.body.scrollHeight : 0;
        parent.postMessage({ type: "fnix-widget-height", widgetId: WID, height: h }, "*");
      } catch (e) { /* noop */ }
    }
    window.sendPrompt = function (text) {
      if (typeof text !== "string" || !text.trim()) return;
      parent.postMessage({ type: "fnix-widget-prompt", widgetId: WID, text: text.slice(0, 4000) }, "*");
    };
    if (typeof ResizeObserver !== "undefined") {
      new ResizeObserver(report).observe(document.documentElement);
    }
    window.addEventListener("load", function () { report(); setTimeout(report, 200); });
    setTimeout(report, 50);
  })();
</script>`;
  return `<!DOCTYPE html><html><head>${csp}${theme}${bridge}</head><body>${code}</body></html>`;
}

function WidgetBlockImpl({ block, onPin, onSendPrompt }: Props) {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [expanded, setExpanded] = useState(true);
  const [iframeHeight, setIframeHeight] = useState<number>(240);
  const [loadError, setLoadError] = useState<string | null>(null);
  const onSendPromptRef = useRef(onSendPrompt);
  onSendPromptRef.current = onSendPrompt;

  // 清洗 + 构造 srcdoc
  const srcDoc = useMemo(() => {
    try {
      const cleaned = sanitizeWidgetCode(block.code);
      return buildSrcDoc(cleaned, block.widgetId);
    } catch (e) {
      // 不在 useMemo 中调用 setState（React Hooks 规则），
      // 错误直接渲染到 iframe 内联展示
      return buildSrcDoc(
        `<div style="color: var(--danger);">清洗失败: ${String(e)}</div>`,
        block.widgetId,
      );
    }
  }, [block.code, block.widgetId]);

  // postMessage 桥：高度上报 + sendPrompt 回灌
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      const iframe = iframeRef.current;
      if (!iframe || e.source !== iframe.contentWindow) return;
      const d = e.data as { type?: string; widgetId?: string; height?: number; text?: string };
      if (!d || d.widgetId !== block.widgetId) return;
      if (d.type === 'fnix-widget-height' && typeof d.height === 'number' && d.height > 0) {
        // 限制在 80-720px 之间，避免过长撑爆对话流
        setIframeHeight(Math.min(720, Math.max(80, d.height + 24)));
      } else if (d.type === 'fnix-widget-prompt' && typeof d.text === 'string') {
        onSendPromptRef.current?.(d.text);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [block.widgetId]);

  // iframe 加载失败监听
  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;
    const onLoad = () => setLoadError(null);
    const onError = () => setLoadError('iframe 加载失败');
    iframe.addEventListener('load', onLoad);
    iframe.addEventListener('error', onError);
    return () => {
      iframe.removeEventListener('load', onLoad);
      iframe.removeEventListener('error', onError);
    };
  }, [srcDoc]);

  // 错误态
  if (loadError) {
    return (
      <div className="cl-widget-wrap cl-widget-error" data-widget-id={block.widgetId}>
        <div className="cl-widget-head">
          <AlertTriangle size={12} className="cl-widget-error-icon" />
          <span className="cl-widget-type">{block.widgetType}</span>
          <span className="cl-widget-error-msg">{loadError}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="cl-widget-wrap" data-widget-id={block.widgetId}>
      <div className="cl-widget-head">
        <button
          type="button"
          className="cl-widget-toggle"
          onClick={() => setExpanded((v) => !v)}
          aria-label={expanded ? '折叠' : '展开'}
        >
          {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        <span className="cl-widget-type">{block.widgetType}</span>
        {block.step && <span className="cl-widget-step">Step {block.step}</span>}
        <div className="cl-widget-actions">
          {onPin && (
            <button
              type="button"
              className="cl-widget-action-btn"
              title="钉到画布"
              onClick={() => onPin({ widgetType: block.widgetType, code: block.code })}
            >
              <Maximize2 size={11} />
            </button>
          )}
        </div>
      </div>
      {expanded && (
        <iframe
          ref={iframeRef}
          title={`widget-${block.widgetId}`}
          sandbox="allow-scripts"
          srcDoc={srcDoc}
          className="cl-widget-iframe"
          style={{ height: `${iframeHeight}px` }}
        />
      )}
    </div>
  );
}

export const WidgetBlock = memo(WidgetBlockImpl);
