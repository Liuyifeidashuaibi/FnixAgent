/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ResultsView — Studio Panel「结果」视图（原 WorkResults，v2 剥离 GlassPanel 外壳）
 * Artifacts | Files | Changes | Preview
 * Version · open · reveal · export · quality status
 *
 * Spec 3: "Preview" tab 升级为真正的 ArtifactCanvas 内联预览
 *          (HTML iframe sandbox / SVG inline / Monaco code / Markdown render)
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Copy,
  Download,
  ExternalLink,
  FileCode2,
  FileText,
  FolderOpen,
  FolderSearch,
  Globe,
  Hammer,
  Layers,
} from "lucide-react";
import type { ArtifactRef } from "./useChatFlow";
import type { WorkExecMode, WorkMission } from "./fnixRuntime";
import { isTauriDesktop } from "./desktopEnv";
import { openArtifactPath, revealArtifactFolder } from "./workDesktop";
import {
  deliverableCoverage,
  formatArtifactVersion,
  qualityLabel,
  type ArtifactQuality,
} from "./artifactMeta";
import { ArtifactCanvas } from "./ArtifactCanvas";
import { getFnixApiBase } from "../../lib/fnixBridge";

type Tab = "artifacts" | "files" | "changes" | "preview";

const TABS: { id: Tab; label: string }[] = [
  { id: "artifacts", label: "产物" },
  { id: "files", label: "文件" },
  { id: "changes", label: "变更" },
  { id: "preview", label: "预览" },
];

function basename(path: string) {
  const p = path.replace(/[/\\]+$/, "");
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i >= 0 ? p.slice(i + 1) : p || path;
}

function extOf(path: string) {
  const b = basename(path);
  const i = b.lastIndexOf(".");
  return i >= 0 ? b.slice(i + 1).toLowerCase() : "";
}

function isHtml(path: string) {
  return /\.html?$/i.test(path);
}

// Spec 3: ArtifactCanvas 支持预览的文件扩展名（与后端 _ALLOWED_PREVIEW_EXT 对齐）
const PREVIEWABLE_EXT = new Set([
  "html", "htm", "svg", "md", "markdown", "txt", "json", "csv",
  "js", "ts", "jsx", "tsx", "css", "scss", "less",
  "py", "rs", "go", "java", "c", "cpp", "h", "hpp",
  "yaml", "yml", "toml", "ini", "sh", "bash",
  "png", "jpg", "jpeg", "gif", "webp", "ico",
]);

function FileIcon({ path }: { path: string }) {
  const ext = extOf(path);
  if (isHtml(path) || ext === "css" || ext === "js" || ext === "ts") {
    return <FileCode2 size={15} />;
  }
  if (ext === "md" || ext === "txt" || ext === "docx" || ext === "pdf") {
    return <FileText size={15} />;
  }
  return <Layers size={15} />;
}

function QualityBadge({ quality }: { quality: ArtifactQuality }) {
  return (
    <span className={`wb-art-q ${quality}`} title={qualityLabel(quality)}>
      {qualityLabel(quality)}
    </span>
  );
}

interface Props {
  artifacts: ArtifactRef[];
  mission: WorkMission | null;
  workMode: WorkExecMode;
  workspace?: string;
  streaming?: boolean;
  canExecutePlan?: boolean;
  onExecutePlan?: () => void;
}

export function ResultsView({
  artifacts,
  mission,
  workMode,
  workspace = "",
  streaming,
  canExecutePlan,
  onExecutePlan,
}: Props) {
  const [tab, setTab] = useState<Tab>("artifacts");
  const [copied, setCopied] = useState(false);
  const [previewIdx, setPreviewIdx] = useState(0);
  // 用户手动切 tab 后不再自动切到 preview，避免 streaming 结束时强制打断用户浏览
  const userTouchedTabRef = useRef(false);
  const isDesktop = isTauriDesktop();
  // Spec 3: preview tab 支持所有可预览类型（html/svg/md/code/image），不只 HTML
  const previewableArts = useMemo(
    () => artifacts.filter((a) => PREVIEWABLE_EXT.has(extOf(a.path))),
    [artifacts],
  );
  const preview = previewableArts[previewIdx] || previewableArts[0] || null;
  const coverage = useMemo(
    () => deliverableCoverage(artifacts, mission?.expected_deliverables),
    [artifacts, mission?.expected_deliverables],
  );

  const previewPath = preview?.path || "";
  useEffect(() => {
    // 仅在用户未手动切 tab 且首次产物出现时自动切 preview，避免 streaming 结束打断用户
    if (previewPath && workMode === "craft" && !streaming && !userTouchedTabRef.current) {
      setTab("preview");
    }
  }, [previewPath, workMode, streaming]);

  // 包装 setTab：用户主动点击 tab 后标记，禁用自动切换
  const switchTab = useCallback((next: Tab) => {
    userTouchedTabRef.current = true;
    setTab(next);
  }, []);

  const emptyHint =
    workMode === "ask"
      ? "Ask（问一问）不写盘。需要交付时切换到 Craft。"
      : workMode === "plan"
        ? "Plan（想一想）只出计划。确认后切 Craft 执行。"
        : "Craft 产物会落在 `.fnix/artifacts/`，直写磁盘，无需 Accept。";

  const exportManifest = () => {
    const payload = {
      exportedAt: new Date().toISOString(),
      workMode,
      workspace,
      mission: mission
        ? {
            title: mission.title,
            expected_deliverables: mission.expected_deliverables,
          }
        : null,
      coverage,
      artifacts: artifacts.map((a) => ({
        path: a.path,
        name: a.name,
        createdAt: a.createdAt,
        source: a.source,
        quality: a.quality,
        version: formatArtifactVersion(a.createdAt),
      })),
    };
    const text = JSON.stringify(payload, null, 2);
    // 加 .catch：浏览器拒绝剪贴板权限（非 HTTPS / 非用户手势）时 Promise reject 静默，
    // 用户以为复制成功但实际没复制。失败时降级为 console 输出 + 短暂提示
    void navigator.clipboard.writeText(text).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      },
      () => {
        // 降级：保留 payload 在控制台供用户手动复制
        console.info("[Fnix] exportManifest clipboard rejected, payload:", text);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1600);
      },
    );
  };

  return (
    <div className="fnx-results">
      {/* ── slim 子工具条：标题 + 计数 + 覆盖率 + 清单导出 ── */}
      <div className="fnx-results-bar">
        <FolderOpen size={15} />
        <span>结果</span>
        <em>{artifacts.length}</em>
        {coverage != null ? <em className="cov">{coverage}%</em> : null}
        <span className="fnx-results-bar-spacer" />
        {artifacts.length > 0 ? (
          <button
            type="button"
            className="wb-mini-btn ghost"
            title="导出产物清单（JSON）"
            onClick={exportManifest}
          >
            {copied ? <Copy size={12} /> : <Download size={12} />}
            {copied ? "已复制清单" : "复制清单"}
          </button>
        ) : null}
      </div>

      {workMode === "plan" && canExecutePlan && !streaming && onExecutePlan ? (
        <div className="wb-plan-cta">
          <p>计划已就绪，可用 Craft 落盘执行。</p>
          <button type="button" className="wb-plan-run" onClick={onExecutePlan}>
            <Hammer size={14} />
            用 Craft 执行
          </button>
        </div>
      ) : null}

      <div className="wb-results-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "on" : ""}
            onClick={() => switchTab(t.id)}
          >
            {t.label}
            {t.id === "artifacts" && artifacts.length > 0 ? (
              <i>{artifacts.length}</i>
            ) : null}
          </button>
        ))}
      </div>

      <div className="wb-results-body">
        {tab === "artifacts" &&
          (artifacts.length === 0 ? (
            <div className="wb-empty">
              <Layers size={22} strokeWidth={1.5} />
              <p>{emptyHint}</p>
            </div>
          ) : (
            <div className="wb-art-list">
              {artifacts.map((a, i) => {
                const q = a.quality || "unknown";
                return (
                  <div key={`${a.path}-${i}`} className="wb-art-row">
                    <button
                      type="button"
                      className="wb-art-item"
                      onClick={() => {
                        // 同步 previewIdx：原代码只 setTab，导致 preview = previewableArts[previewIdx]
                        // 仍显示第 0 项，用户点第 3 个 artifact 看到的是第 1 个内容
                        const idx = previewableArts.findIndex((p) => p.path === a.path);
                        if (idx >= 0) setPreviewIdx(idx);
                        switchTab(isHtml(a.path) ? "preview" : "files");
                      }}
                      title={a.path}
                    >
                      <span className="wb-art-ico">
                        <FileIcon path={a.path} />
                      </span>
                      <span className="wb-art-meta">
                        <b>{a.name || basename(a.path)}</b>
                        <span>
                          {formatArtifactVersion(a.createdAt)}
                          {a.source ? ` · ${a.source}` : ""}
                        </span>
                      </span>
                      <QualityBadge quality={q} />
                      <span className="wb-art-ext">{extOf(a.path) || "文件"}</span>
                    </button>
                    {isDesktop ? (
                      <>
                        <button
                          type="button"
                          className="wb-art-open"
                          title="打开文件"
                          onClick={() => void openArtifactPath(a.path, workspace)}
                        >
                          <ExternalLink size={13} />
                        </button>
                        <button
                          type="button"
                          className="wb-art-open"
                          title="在文件夹中显示"
                          onClick={() => void revealArtifactFolder(a.path, workspace)}
                        >
                          <FolderSearch size={13} />
                        </button>
                      </>
                    ) : null}
                  </div>
                );
              })}
            </div>
          ))}

        {tab === "files" &&
          (artifacts.length === 0 ? (
            <div className="wb-empty">
              <FileText size={22} strokeWidth={1.5} />
              <p>本回合尚未写入文件。</p>
            </div>
          ) : (
            <ul className="wb-file-list">
              {artifacts.map((a, i) => (
                <li key={`${a.path}-${i}`}>
                  <FileIcon path={a.path} />
                  <code>{a.path}</code>
                  <QualityBadge quality={a.quality || "unknown"} />
                </li>
              ))}
            </ul>
          ))}

        {tab === "changes" && (
          <div className="wb-empty left">
            {workMode === "craft" ? (
              <>
                <p>
                  <strong>Craft</strong> 变更已直写磁盘
                  {artifacts.length ? `（${artifacts.length} 个文件）` : ""}。
                </p>
                <p className="dim">打开仓库后可在会话内预览并确认变更。</p>
              </>
            ) : (
              <p>
                <strong>{workMode === "ask" ? "Ask" : "Plan"}</strong> 本回合不写盘，无待
                Accept 变更。
              </p>
            )}
            {mission?.expected_deliverables ? (
              <div className="wb-deliver">
                <span>预期交付</span>
                <p>
                  {Array.isArray(mission.expected_deliverables)
                    ? mission.expected_deliverables.join(" · ")
                    : String(mission.expected_deliverables)}
                </p>
                {coverage != null ? (
                  <p className="dim">覆盖率 {coverage}%（相对 expected_deliverables）</p>
                ) : null}
              </div>
            ) : null}
          </div>
        )}

        {tab === "preview" &&
          (preview ? (
            <div className="wb-preview-canvas">
              {/* Spec 3: 真正的 ArtifactCanvas 内联预览 */}
              <ArtifactCanvas
                artifact={preview}
                apiBase={getFnixApiBase()}
                workspace={workspace}
              />
              {/* 多产物切换器 */}
              {previewableArts.length > 1 ? (
                <div className="wb-preview-switcher" role="tablist">
                  {previewableArts.map((a, i) => (
                    <button
                      key={`${a.path}-${i}`}
                      type="button"
                      role="tab"
                      aria-selected={previewIdx === i}
                      className={previewIdx === i ? "on" : ""}
                      onClick={() => setPreviewIdx(i)}
                      title={a.path}
                    >
                      <FileIcon path={a.path} />
                      <span>{a.name || basename(a.path)}</span>
                    </button>
                  ))}
                </div>
              ) : null}
              {/* Desktop 操作（保留向后兼容） */}
              {isDesktop ? (
                <div className="wb-preview-actions-legacy">
                  <button
                    type="button"
                    className="wb-mini-btn"
                    onClick={() => void openArtifactPath(preview.path, workspace)}
                  >
                    <ExternalLink size={12} /> 系统打开
                  </button>
                  <button
                    type="button"
                    className="wb-mini-btn"
                    onClick={() => void revealArtifactFolder(preview.path, workspace)}
                  >
                    <FolderSearch size={12} /> 所在文件夹
                  </button>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="wb-empty">
              <Globe size={22} strokeWidth={1.5} />
              <p>暂无可预览产物。Craft 任务完成后 HTML / 代码 / 图片 / Markdown 会出现在此。</p>
            </div>
          ))}
      </div>
    </div>
  );
}
