/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Spec 3: Artifact 协同编辑器
 * ============================================================
 * 对标:
 *   - 画布编辑 的增量编辑体验
 *   - 内联编辑 + 光标闪烁
 *   - Aider 的 SEARCH/REPLACE block 应用
 *   - VSCode 官方推荐用法 (OnMount monaco / DiffEditor / createDecorationsCollection)
 *
 * 设计要点 (基于 @monaco-editor/react v4.6+ 与 monaco-editor v0.40+ 最佳实践):
 *   1. monaco 实例从 OnMount 第二参数获取,杜绝动态 import 的多实例风险
 *   2. deltaDecorations 已废弃,改用 editor.createDecorationsCollection + collection.set/clear
 *   3. diff 模式用 <DiffEditor> 组件 (monaco.editor.createDiffEditor),自带 +/- 标记 + 滚动同步
 *   4. patch 应用通过 onAcceptPatch 回调上抛,父组件负责落盘
 *   5. automaticLayout: true 应对 tab 切换/侧栏折叠时的尺寸变化
 *   6. glyphMargin: true 显式开启,给 ai-edit-glyph 留位置
 *
 * AI 编辑光标 awareness:
 *   - 应用 patch 后,在 Monaco 中用 createDecorationsCollection 标记改动行
 *   - CSS 动画 ai-edit-flash 2.2 秒后消退
 *   - 同时在 overviewRuler / minimap 标记,便于大文件定位
 *
 * 安全:
 *   - 用户编辑需点击"保存"显式提交,不自动保存(避免误改)
 *   - AI patch 应用后,展示 diff 预览,用户确认后才落盘
 */

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  Code2,
  Edit3,
  GitCompare,
  Save,
  Undo2,
  X,
} from "lucide-react";
import Editor, { DiffEditor, type OnMount, type DiffOnMount } from "@monaco-editor/react";
import type * as monaco from "monaco-editor";
import {
  applyPatches,
  parseSearchReplace,
  type SearchReplaceBlock,
} from "./artifactPatch";

interface Props {
  /** 原始内容 */
  initialContent: string;
  /** 文件路径(用于显示) */
  path: string;
  /** 语言(传给 Monaco) */
  language: string;
  /** 保存回调 */
  onSave: (newContent: string) => Promise<void>;
  /** 可选:外部传入的 AI patch(自动触发应用) */
  pendingPatch?: string | null;
  /** patch 应用后的回调(清空 pendingPatch 状态) */
  onPatchConsumed?: () => void;
}

type Mode = "view" | "edit" | "diff";

interface LineRange {
  start: number;
  end: number;
}

export function ArtifactEditor({
  initialContent,
  path,
  language,
  onSave,
  pendingPatch,
  onPatchConsumed,
}: Props) {
  const [content, setContent] = useState(initialContent);
  const [mode, setMode] = useState<Mode>("view");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [patchBlocks, setPatchBlocks] = useState<SearchReplaceBlock[] | null>(null);
  const [patchedContent, setPatchedContent] = useState<string | null>(null);
  const [patchErrors, setPatchErrors] = useState<string[]>([]);
  /** 待闪烁的改动行范围(在 patchedContent 中) */
  const [pendingFlashRanges, setPendingFlashRanges] = useState<LineRange[]>([]);

  // monaco 实例与 editor 实例 — 通过 OnMount 第二参数同步获取,杜绝动态 import
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof monaco | null>(null);
  const diffEditorRef = useRef<monaco.editor.IStandaloneDiffEditor | null>(null);
  // decorations collection — monaco v0.34+ 推荐用法,替代已废弃的 deltaDecorations
  const aiDecorationsRef = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const diffDecorationsRef = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const flashTimerRef = useRef<number>(0);

  // Monaco 挂载时保存引用(单 Editor)
  const handleMount: OnMount = useCallback((editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
  }, []);

  // DiffEditor 挂载时保存引用 + 监听 diff 完成后高亮 modified 侧
  const handleDiffMount: DiffOnMount = useCallback((diffEditor, monaco) => {
    diffEditorRef.current = diffEditor as unknown as monaco.editor.IStandaloneDiffEditor;
    monacoRef.current = monaco;

    const de = diffEditor as unknown as monaco.editor.IStandaloneDiffEditor;
    const modified = de.getModifiedEditor();

    // diff 计算完成后,高亮 modified 侧改动行(用户进入 diff 模式即可看到闪动)
    de.onDidUpdateDiff(() => {
      const changes = de.getLineChanges() ?? [];
      const lines: number[] = [];
      for (const c of changes) {
        // c.modifiedEndLineNumber === 0 表示纯删除,跳过
        const start = c.modifiedStartLineNumber;
        const end = c.modifiedEndLineNumber || start;
        for (let l = start; l <= end; l++) lines.push(l);
      }
      if (lines.length === 0) return;

      // 复用 collection,避免每次新建
      if (!diffDecorationsRef.current) {
        diffDecorationsRef.current = modified.createDecorationsCollection([]);
      }
      const collection = diffDecorationsRef.current;
      collection.set(
        lines.map((l) => ({
          range: new monaco.Range(l, 1, l, 1),
          options: {
            isWholeLine: true,
            className: "fnix-ai-just-edited",
            glyphMarginClassName: "fnix-ai-edit-glyph",
            overviewRuler: {
              color: "#4a6fa5",
              position: monaco.editor.OverviewRulerLane.Right,
            },
          } satisfies monaco.editor.IModelDecorationOptions,
        })),
      );
      // 2.2s 后淡出
      window.clearTimeout(flashTimerRef.current);
      flashTimerRef.current = window.setTimeout(() => {
        collection.clear();
      }, 2200);
    });
  }, []);

  // 外部内容变化(切换 artifact) — 重置全部状态
  useEffect(() => {
    setContent(initialContent);
    setDirty(false);
    setPatchBlocks(null);
    setPatchedContent(null);
    setPatchErrors([]);
    setPendingFlashRanges([]);
    setMode("view");
    // 清理装饰
    aiDecorationsRef.current?.clear();
    diffDecorationsRef.current?.clear();
  }, [initialContent, path]);

  // 用户编辑触发 dirty
  const handleChange = useCallback(
    (value: string | undefined) => {
      const next = value ?? "";
      setContent(next);
      setDirty(next !== initialContent);
    },
    [initialContent],
  );

  // 保存
  const handleSave = useCallback(async () => {
    if (!dirty) return;
    setSaving(true);
    try {
      await onSave(content);
      setDirty(false);
      setMode("view");
    } finally {
      setSaving(false);
    }
  }, [content, dirty, onSave]);

  // 撤销
  const handleReset = useCallback(() => {
    setContent(initialContent);
    setDirty(false);
    setMode("view");
  }, [initialContent]);

  // 接收外部 AI patch,进入 diff 预览模式
  // 用 ref 锁住已消费的 patch 字符串,避免 React StrictMode 双渲染 / 父组件重渲染
  // 导致 useEffect 重复执行 (重复时 content 已是 patched,SEARCH 自然找不到)
  const consumedPatchRef = useRef<string | null>(null);
  useEffect(() => {
    if (!pendingPatch) return;
    // 已消费过同一个 patch → 跳过
    if (consumedPatchRef.current === pendingPatch) return;
    consumedPatchRef.current = pendingPatch;

    const blocks = parseSearchReplace(pendingPatch);
    if (blocks.length === 0) {
      setPatchErrors(["未找到任何 SEARCH/REPLACE block"]);
      setMode("diff");
      onPatchConsumed?.();
      return;
    }
    const result = applyPatches(content, blocks);
    setPatchBlocks(blocks);
    setPatchedContent(result.content);
    setPatchErrors(
      result.results.filter((r) => !r.applied).map((r) => r.error || "未知错误"),
    );
    setMode("diff");
    onPatchConsumed?.();
    // 故意省略 content / onPatchConsumed 依赖:只对 pendingPatch 本身响应
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPatch]);

  // 计算两个文本的逐行 diff,返回改动行范围(基于 newLines 的行号,1-based)
  function computeChangedLineRanges(oldText: string, newText: string): LineRange[] {
    const oldLines = oldText.split("\n");
    const newLines = newText.split("\n");
    const maxLen = Math.max(oldLines.length, newLines.length);
    const ranges: LineRange[] = [];
    let start = -1;
    for (let i = 0; i < maxLen; i++) {
      const changed = oldLines[i] !== newLines[i];
      if (changed && start < 0) start = i + 1;
      if ((!changed || i === maxLen - 1) && start > 0) {
        const end = changed ? i + 1 : i;
        ranges.push({ start, end });
        start = -1;
      }
    }
    return ranges;
  }

  // 在单 Editor 中闪烁指定行范围(应用 patch 后调用)
  const flashLines = useCallback((ranges: LineRange[]) => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco || ranges.length === 0) return;

    if (!aiDecorationsRef.current) {
      aiDecorationsRef.current = editor.createDecorationsCollection([]);
    }
    const collection = aiDecorationsRef.current;

    // 展开行范围成行号数组
    const lineNumbers: number[] = [];
    for (const r of ranges) {
      for (let l = r.start; l <= r.end; l++) lineNumbers.push(l);
    }

    collection.set(
      lineNumbers.map((l) => ({
        range: new monaco.Range(l, 1, l, 1),
        options: {
          isWholeLine: true,
          className: "fnix-ai-just-edited",
          glyphMarginClassName: "fnix-ai-edit-glyph",
          overviewRuler: {
            color: "#4a6fa5",
            position: monaco.editor.OverviewRulerLane.Right,
          },
        } satisfies monaco.editor.IModelDecorationOptions,
      })),
    );

    // 滚动到第一处改动
    if (ranges[0]) editor.revealLineInCenter(ranges[0].start);

    // 2.2s 后清除高亮
    window.clearTimeout(flashTimerRef.current);
    flashTimerRef.current = window.setTimeout(() => {
      collection.clear();
    }, 2200);
  }, []);

  // 应用 patch(用户确认) — 落盘 + 切回 edit 模式 + 闪烁改动行
  const handleApplyPatch = useCallback(async () => {
    if (!patchedContent) return;
    const flashRanges = computeChangedLineRanges(content, patchedContent);
    setContent(patchedContent);
    setDirty(patchedContent !== initialContent);
    setPatchBlocks(null);
    setPatchedContent(null);
    setMode("edit");
    setPendingFlashRanges(flashRanges);
    // 自动保存
    try {
      setSaving(true);
      await onSave(patchedContent);
      setDirty(false);
    } finally {
      setSaving(false);
    }
  }, [patchedContent, content, initialContent, onSave]);

  // mode 切回 edit 后,等 Editor 重新挂载,触发闪烁
  useEffect(() => {
    if (mode !== "edit" || pendingFlashRanges.length === 0) return;
    // requestAnimationFrame 等 React commit + monaco 渲染完成
    const raf = requestAnimationFrame(() => {
      flashLines(pendingFlashRanges);
      setPendingFlashRanges([]);
    });
    return () => cancelAnimationFrame(raf);
  }, [mode, pendingFlashRanges, flashLines]);

  // 拒绝 patch
  const handleRejectPatch = useCallback(() => {
    setPatchBlocks(null);
    setPatchedContent(null);
    setPatchErrors([]);
    setMode("view");
  }, []);

  // 组件卸载时清理 timer + collection
  useEffect(
    () => () => {
      window.clearTimeout(flashTimerRef.current);
      aiDecorationsRef.current?.clear();
      diffDecorationsRef.current?.clear();
    },
    [],
  );

  return (
    <div className="fnix-art-editor">
      <div className="fnix-art-editor-bar">
        <div className="fnix-art-editor-bar-l">
          <Code2 size={13} />
          <span className="fnix-art-editor-path">{path}</span>
          {dirty && <span className="fnix-art-editor-dirty">未保存</span>}
        </div>
        <div className="fnix-art-editor-bar-r">
          {mode === "view" && (
            <button
              type="button"
              className="fnix-art-editor-btn"
              onClick={() => setMode("edit")}
              title="进入编辑模式"
            >
              <Edit3 size={12} /> 编辑
            </button>
          )}
          {mode === "edit" && (
            <>
              <button
                type="button"
                className="fnix-art-editor-btn"
                onClick={handleReset}
                disabled={!dirty || saving}
                title="放弃修改"
              >
                <Undo2 size={12} /> 撤销
              </button>
              <button
                type="button"
                className="fnix-art-editor-btn primary"
                onClick={handleSave}
                disabled={!dirty || saving}
                title="保存到文件"
              >
                <Save size={12} /> {saving ? "保存中…" : "保存"}
              </button>
            </>
          )}
          {mode === "diff" && (
            <>
              <span className="fnix-art-editor-diff-info">
                {patchErrors.length > 0
                  ? `${patchErrors.length} 处无法应用`
                  : `${patchBlocks?.length || 0} 处变更待确认`}
              </span>
              <button
                type="button"
                className="fnix-art-editor-btn"
                onClick={handleRejectPatch}
                title="拒绝此次 AI 编辑"
              >
                <X size={12} /> 拒绝
              </button>
              <button
                type="button"
                className="fnix-art-editor-btn primary"
                onClick={handleApplyPatch}
                disabled={patchErrors.length > 0 || !patchedContent}
                title="应用变更并保存"
              >
                <Check size={12} /> 应用
              </button>
              <button
                type="button"
                className="fnix-art-editor-btn"
                onClick={() => setMode("view")}
                title="返回查看模式"
              >
                <GitCompare size={12} /> 取消
              </button>
            </>
          )}
        </div>
      </div>

      <div className="fnix-art-editor-body">
        {mode === "diff" && patchedContent ? (
          <DiffEditor
            // key 强制重置,避免不同 patch 之间脏状态
            key={`diff-${path}-${patchBlocks?.length ?? 0}`}
            original={content}
            modified={patchedContent}
            language={language}
            theme="vs"
            onMount={handleDiffMount}
            options={{
              renderSideBySide: true,
              originalEditable: false,
              readOnly: true,
              renderMarginRevertIcon: false,
              enableSplitViewResizing: true,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              fontSize: 13,
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
              wordWrap: "on",
            }}
          />
        ) : (
          <Editor
            // mode 切换时强制重置,确保 readOnly 等选项立即生效
            key={`single-${mode}-${path}`}
            height="100%"
            language={language}
            value={content}
            theme="vs"
            onMount={handleMount}
            onChange={handleChange}
            options={{
              readOnly: mode === "view",
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
              lineNumbers: "on",
              scrollBeyondLastLine: false,
              wordWrap: "on",
              renderWhitespace: "selection",
              smoothScrolling: true,
              cursorBlinking: "smooth",
              padding: { top: 12, bottom: 12 },
              glyphMargin: true,
              automaticLayout: true,
            }}
          />
        )}
      </div>

      {patchErrors.length > 0 && mode === "diff" && (
        <div className="fnix-art-editor-errors">
          <strong>以下 SEARCH 段未找到精确匹配:</strong>
          <ul>
            {patchErrors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
