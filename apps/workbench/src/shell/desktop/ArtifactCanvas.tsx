/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Spec 3: ArtifactCanvas — 产物画布
 * ============================================================
 * 真正的内联预览 + 编辑（内联预览与编辑）
 *
 * 支持类型：
 *   - HTML: iframe sandbox srcdoc（隔离 DOM，allow-scripts 不加 allow-same-origin）
 *   - SVG: 直接内联渲染
 *   - Markdown: react-markdown + remark-gfm + rehype-highlight（支持表格/任务列表/Mermaid）
 *   - 代码 (js/ts/css/py/rs/go 等): ArtifactEditor（可编辑 + AI patch 增量编辑）
 *   - 图片 (png/jpg/gif/webp/svg): 直接显示
 *   - 文本 (txt/json/csv/yaml): ArtifactEditor 纯文本
 *
 * 用户体验：
 *   - 顶部工具栏：文件名 · 类型 · 大小 · 复制 · 下载 · 在浏览器打开 · 切换"源码/预览/编辑"
 *   - 双视图模式（HTML/MD）：左侧源码，右侧预览
 *   - 单视图模式（其他）：直接渲染
 *   - 编辑模式（除图片外）：调用 ArtifactEditor，支持 SEARCH/REPLACE patch 增量编辑
 *   - 新中式宋韵风：青灰主色 / 茶白底 / 思源宋体 / 细线轴
 *
 * Spec 3 改进点：
 *   - react-markdown 替换正则渲染器
 *   - Mermaid 代码块实时渲染
 *   - 增量编辑 SEARCH/REPLACE（参考业界最佳实践 + 内联编辑）
 *   - Monaco DiffEditor + createDecorationsCollection（VSCode 官方推荐）
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import {
  Code2,
  Copy,
  Download,
  Edit3,
  Eye,
  ExternalLink,
  FileText,
  Image as ImageIcon,
  LayoutPanelLeft,
} from "lucide-react";
import Editor from "@monaco-editor/react";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { ArtifactEditor } from "./ArtifactEditor";
import { writeArtifact, authHeaders } from "../../lib/fnixBridge";

export interface ArtifactContent {
  ok: boolean;
  path: string;
  name: string;
  ext: string;
  size: number;
  mime: string;
  encoding: "utf-8" | "base64";
  content: string;
  is_svg?: boolean;
  is_html?: boolean;
  is_markdown?: boolean;
  error?: string;
}

export type ViewMode = "preview" | "source" | "split" | "edit";

interface Props {
  artifact: { path: string; name?: string } | null;
  apiBase: string;
  /** 关闭回调（用于在父级隐藏 Canvas） */
  onClose?: () => void;
  /** 当前 workspace 路径 */
  workspace?: string;
}

const EXT_LANG_MAP: Record<string, string> = {
  js: "javascript", jsx: "javascript",
  ts: "typescript", tsx: "typescript",
  css: "css", scss: "scss", less: "less",
  py: "python", rs: "rust", go: "go",
  java: "java", c: "c", cpp: "cpp", h: "c", hpp: "cpp",
  json: "json", yaml: "yaml", yml: "yaml",
  toml: "ini", ini: "ini", sh: "shell", bash: "shell",
  html: "html", htm: "html", md: "markdown", markdown: "markdown",
  xml: "xml", sql: "sql",
};

function extOf(path: string): string {
  const b = path.replace(/[/\\]+$/, "").split(/[/\\]/).pop() || "";
  const i = b.lastIndexOf(".");
  return i >= 0 ? b.slice(i + 1).toLowerCase() : "";
}

function sizeLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

/**
 * 判断是否可编辑（用于决定是否显示"编辑"按钮）
 * 图片不可编辑；HTML/SVG/MD/代码/文本均可编辑
 */
function isEditable(isImage: boolean): boolean {
  return !isImage;
}

/**
 * 调用后端 /artifacts/write 写入文件
 * 失败时抛错，由调用方处理
 */
async function saveArtifact(path: string, content: string, workspace?: string): Promise<void> {
  const result = await writeArtifact({ path, content, workspace });
  if (!result.ok) {
    throw new Error(result.error || "写入失败");
  }
}

export function ArtifactCanvas({ artifact, apiBase, onClose, workspace }: Props) {
  const [data, setData] = useState<ArtifactContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("preview");
  const [copied, setCopied] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const ext = useMemo(() => (artifact ? extOf(artifact.path) : ""), [artifact]);

  // 默认视图模式：HTML/MD 用 split，其他用 preview
  useEffect(() => {
    if (!ext) return;
    if (ext === "html" || ext === "htm" || ext === "md" || ext === "markdown") {
      setViewMode("split");
    } else {
      setViewMode("preview");
    }
  }, [ext]);

  // 加载文件内容
  const loadContent = useCallback(async () => {
    if (!artifact) return;
    setLoading(true);
    setError(null);
    try {
      const url = `${apiBase}/api/v1/work/artifacts/read?path=${encodeURIComponent(artifact.path)}`;
      // 与 streamWork/fnixRuntime 一致：携带 capability token，否则鉴权环境 401 仅显示"加载失败"，
      // 用户不知是鉴权问题。writeArtifact 路径已带 authHeaders，此处读取补齐。
      const resp = await fetch(url, { headers: authHeaders() });
      const json = (await resp.json()) as ArtifactContent;
      if (!json.ok) {
        setError(json.error || "加载失败");
        setData(null);
      } else {
        setData(json);
      }
    } catch (e) {
      setError(String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [artifact, apiBase]);

  useEffect(() => {
    if (artifact) {
      void loadContent();
    } else {
      setData(null);
      setError(null);
    }
  }, [artifact, loadContent]);

  // 复制内容
  const handleCopy = useCallback(() => {
    if (!data) return;
    void navigator.clipboard.writeText(data.content).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  }, [data]);

  // 下载
  const handleDownload = useCallback(() => {
    if (!data) return;
    const blob = new Blob([data.content], { type: data.mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = data.name;
    a.click();
    URL.revokeObjectURL(url);
  }, [data]);

  // 在浏览器打开（仅 HTML）
  const handleOpenExternal = useCallback(() => {
    if (!data) return;
    if (data.is_html) {
      const blob = new Blob([data.content], { type: "text/html" });
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    }
  }, [data]);

  // 保存编辑（ArtifactEditor 调用）
  const handleSave = useCallback(
    async (newContent: string) => {
      if (!data) return;
      setSaveError(null);
      try {
        await saveArtifact(data.path, newContent, workspace);
        // 更新本地缓存，避免下次 loadContent 覆盖编辑结果
        setData({ ...data, content: newContent, size: newContent.length });
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setSaveError(msg);
        throw e; // 上抛让 ArtifactEditor 显示失败状态
      }
    },
    [data, workspace],
  );

  // ─── 渲染逻辑 ──────────────────────────────────────────────

  if (!artifact) {
    return (
      <div className="fnix-canvas fnix-canvas-empty">
        <LayoutPanelLeft size={28} strokeWidth={1.5} />
        <p>从左侧 Results 选择产物即可预览</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="fnix-canvas fnix-canvas-loading">
        <div className="fnix-canvas-spinner" />
        <p>载入中…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="fnix-canvas fnix-canvas-error">
        <FileText size={28} strokeWidth={1.5} />
        <p>无法预览此产物</p>
        <code>{error}</code>
        <button type="button" className="fnix-canvas-retry" onClick={loadContent}>
          重试
        </button>
      </div>
    );
  }

  if (!data) return null;

  const isImage = data.encoding === "base64";
  const isHtml = !!data.is_html;
  const isSvg = !!data.is_svg;
  const isMarkdown = !!data.is_markdown;
  const isCode = !isHtml && !isSvg && !isMarkdown && !isImage;
  const monacoLang = EXT_LANG_MAP[ext] || "plaintext";
  const canSwitchView = isHtml || isMarkdown;
  const canEdit = isEditable(isImage);

  // HTML srcdoc（加 CSP 限制外部资源）
  const htmlSrcDoc = isHtml
    ? data.content.replace(
        /<head>/i,
        `<head><meta http-equiv="Content-Security-Policy" content="default-src 'unsafe-inline' 'unsafe-eval' data:; img-src 'unsafe-inline' data: https:; connect-src 'none';"></meta>`,
      )
    : "";

  // 图片 data URL
  const imgDataUrl = isImage
    ? `data:${data.mime};base64,${data.content}`
    : "";

  return (
    <div className="fnix-canvas">
      {/* 工具栏 */}
      <div className="fnix-canvas-bar">
        <div className="fnix-canvas-bar-l">
          {isHtml ? <Eye size={14} /> : isImage ? <ImageIcon size={14} /> : <Code2 size={14} />}
          <span className="fnix-canvas-name">{data.name}</span>
          <span className="fnix-canvas-meta">
            {ext.toUpperCase()} · {sizeLabel(data.size)}
          </span>
        </div>
        <div className="fnix-canvas-bar-r">
          {canSwitchView && (
            <div className="fnix-canvas-seg">
              <button
                type="button"
                className={viewMode === "preview" ? "on" : ""}
                onClick={() => setViewMode("preview")}
                title="仅预览"
              >
                <Eye size={12} /> 预览
              </button>
              <button
                type="button"
                className={viewMode === "source" ? "on" : ""}
                onClick={() => setViewMode("source")}
                title="仅源码"
              >
                <Code2 size={12} /> 源码
              </button>
              <button
                type="button"
                className={viewMode === "split" ? "on" : ""}
                onClick={() => setViewMode("split")}
                title="双视图"
              >
                <LayoutPanelLeft size={12} /> 双视图
              </button>
            </div>
          )}
          {canEdit && (
            <button
              type="button"
              className={`fnix-canvas-btn ${viewMode === "edit" ? "on" : ""}`}
              onClick={() => setViewMode(viewMode === "edit" ? "preview" : "edit")}
              title={viewMode === "edit" ? "退出编辑" : "编辑此文件"}
            >
              <Edit3 size={13} /> {viewMode === "edit" ? "返回" : "编辑"}
            </button>
          )}
          <button
            type="button"
            className="fnix-canvas-btn"
            onClick={handleCopy}
            title="复制内容"
          >
            {copied ? <Copy size={13} /> : <Copy size={13} />}
            {copied ? "已复制" : "复制"}
          </button>
          <button
            type="button"
            className="fnix-canvas-btn"
            onClick={handleDownload}
            title="下载"
          >
            <Download size={13} /> 下载
          </button>
          {isHtml && (
            <button
              type="button"
              className="fnix-canvas-btn"
              onClick={handleOpenExternal}
              title="在新窗口打开"
            >
              <ExternalLink size={13} /> 新窗口
            </button>
          )}
          {onClose && (
            <button
              type="button"
              className="fnix-canvas-btn fnix-canvas-close"
              onClick={onClose}
              title="关闭"
            >
              ×
            </button>
          )}
        </div>
      </div>

      {/* 内容区 */}
      <div className={`fnix-canvas-body mode-${viewMode}`}>
        {/* 编辑模式：ArtifactEditor 接管整个内容区 */}
        {viewMode === "edit" && canEdit ? (
          <div className="fnix-canvas-pane edit full">
            <ArtifactEditor
              initialContent={data.content}
              path={data.path}
              language={monacoLang}
              onSave={handleSave}
            />
          </div>
        ) : (
          <>
            {/* HTML 预览 */}
            {isHtml && (viewMode === "preview" || viewMode === "split") && (
              <div className="fnix-canvas-pane preview">
                <iframe
                  ref={iframeRef}
                  title="artifact-preview"
                  sandbox="allow-scripts"
                  srcDoc={htmlSrcDoc}
                  className="fnix-canvas-iframe"
                />
              </div>
            )}

            {/* SVG 预览 */}
            {isSvg && (
              <div className="fnix-canvas-pane preview svg">
                <div
                  className="fnix-canvas-svg"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(data.content, { USE_PROFILES: { svg: true, svgFilters: true } }) }}
                />
              </div>
            )}

            {/* Markdown 预览 */}
            {isMarkdown && (viewMode === "preview" || viewMode === "split") && (
              <div className="fnix-canvas-pane preview markdown">
                <MarkdownRenderer content={data.content} />
              </div>
            )}

            {/* 图片预览 */}
            {isImage && (
              <div className="fnix-canvas-pane preview image">
                <img src={imgDataUrl} alt={data.name} className="fnix-canvas-img" />
              </div>
            )}

            {/* 源码（HTML/MD 双视图，或纯代码） */}
            {(isHtml || isMarkdown
              ? viewMode === "source" || viewMode === "split"
              : isCode) && (
              <div className={`fnix-canvas-pane source ${(isHtml || isMarkdown) ? "" : "full"}`}>
                <Editor
                  height="100%"
                  language={monacoLang}
                  value={data.content}
                  theme="vs"
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    fontSize: 13,
                    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
                    lineNumbers: "on",
                    scrollBeyondLastLine: false,
                    wordWrap: "on",
                    renderWhitespace: "selection",
                    smoothScrolling: true,
                    cursorBlinking: "smooth",
                    padding: { top: 12, bottom: 12 },
                  }}
                />
              </div>
            )}
          </>
        )}
      </div>

      {/* 保存错误提示 */}
      {saveError && (
        <div className="fnix-canvas-save-error" role="alert">
          <strong>保存失败:</strong> <code>{saveError}</code>
          <button
            type="button"
            className="fnix-canvas-save-error-dismiss"
            onClick={() => setSaveError(null)}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
