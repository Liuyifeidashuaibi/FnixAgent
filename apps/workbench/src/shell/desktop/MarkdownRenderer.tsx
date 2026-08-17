/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Spec 3: Markdown 渲染器
 * ============================================================
 * 对标: 流式 Markdown 渲染方案 (https://github.com/流式 Markdown 渲染方案)
 *
 * 设计:
 *   - react-markdown 10 + remark-gfm (表格/任务列表/删除线/autolink)
 *   - rehype-highlight 代码块语法高亮 (highlight.js 已在 deps)
 *   - Mermaid 代码块分流到 MermaidBlock 组件
 *   - 与 ArtifactCanvas 的茶白底 + 青灰主色风格一致
 *
 * 与原 renderMarkdown(正则) 的差异:
 *   - 支持嵌套列表(原版只能一层)
 *   - 支持表格(原版完全无)
 *   - 支持任务列表 - [x]
 *   - 支持删除线 ~~text~~
 *   - 代码块语法高亮
 *   - 流式渲染不闪烁(react-markdown 内部用增量 AST 更新)
 */

import { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import type { Components } from "react-markdown";
import { MermaidBlock } from "./MermaidBlock";

interface Props {
  /** Markdown 源文本 */
  content: string;
  /** 是否启用 GFM (表格/任务列表/删除线),默认开 */
  gfm?: boolean;
  /** 是否启用语法高亮,默认开 */
  highlight?: boolean;
}

/**
 * 自定义 components:
 *   - code: 区分 inline / block,block 中区分 mermaid / 普通
 *   - a: 强制 target=_blank + rel=noopener
 *   - table: 加 class 便于 CSS
 */
const components: Components = {
  code(props) {
    const { className, children, ...rest } = props;
    const text = String(children ?? "");
    // inline code (no className, no newline)
    const isInline = !className && !text.includes("\n");
    if (isInline) {
      return (
        <code className="md-inline" {...rest}>
          {children}
        </code>
      );
    }
    // 提取语言
    const match = /language-(\w+)/.exec(className || "");
    const lang = match?.[1]?.toLowerCase();
    // Mermaid 分流
    if (lang === "mermaid") {
      // 去掉末尾换行
      const code = text.replace(/\n$/, "");
      return <MermaidBlock code={code} />;
    }
    // 普通代码块:用 rehype-highlight 高亮(已被插件处理),只加 class
    return (
      <code className={className ? `md-code-block ${className}` : "md-code-block"} {...rest}>
        {children}
      </code>
    );
  },
  a(props) {
    const { href, children, ...rest } = props;
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    );
  },
  table(props) {
    return <table className="md-table" {...props} />;
  },
  th(props) {
    return <th className="md-th" {...props} />;
  },
  td(props) {
    return <td className="md-td" {...props} />;
  },
};

function MarkdownRendererImpl({ content, gfm = true, highlight = true }: Props) {
  const remarkPlugins = useMemo(() => (gfm ? [remarkGfm] : []), [gfm]);
  const rehypePlugins = useMemo(
    () => (highlight ? [rehypeHighlight] : []),
    [highlight],
  );

  return (
    <div className="fnix-md">
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export const MarkdownRenderer = memo(MarkdownRendererImpl);
