/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Composer — thin shell wrapper over GlassComposer + AttachMenu.
 * 内置 @file 补全：检测光标前最后一个 @ 后的查询串，
 * 弹出文件列表 popover（桌面环境读取本地文件，浏览器 dev 显示提示）。
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react';
import type { ChatAttachment } from '../../utils/tauri';
import { GlassComposer } from '../../ui/glass';
import { AttachMenu } from './AttachMenu';
import { isTauriDesktop } from './desktopEnv';

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop?: () => void;
  streaming: boolean;
  placeholder?: string;
  autoFocus?: boolean;
  compact?: boolean;
  /** Composer 底栏右侧插槽（模型 pill 等）。父级始终通过此 slot 传入。 */
  modelSlot?: ReactNode;
  /** Composer 底栏左侧额外插槽（WorkModePicker 等），在加号菜单之后 */
  leftExtraSlot?: ReactNode;
  attachments?: ChatAttachment[];
  onPickFiles?: (files: FileList) => void;
  onRemoveAttachment?: (id: string) => void;
  onPickFolder?: () => void;
  projectPath?: string;
  /** 工作区显示名（传入加号菜单显示当前 workspace） */
  projectLabel?: string;
  /** 外部禁用发送（如 Code 模式未打开仓库时） */
  sendDisabled?: boolean;
}

interface MentionItem {
  name: string;
  path: string;
  isDir: boolean;
  relPath: string;
}

interface MentionRange {
  /** Index of the `@` character in value. */
  at: number;
  /** Index just after `@` (start of query). */
  start: number;
  /** Index at end of query (cursor position). */
  end: number;
}

interface MentionTrigger {
  range: MentionRange;
  query: string;
}

/** Directories to skip when walking the project tree. */
const IGNORE_DIRS = new Set([
  'node_modules',
  '.git',
  '.svn',
  '.hg',
  '.next',
  '.nuxt',
  '.turbo',
  '.parcel-cache',
  'dist',
  'build',
  'out',
  'target',
  'debug',
  'release',
  '.cache',
  '.venv',
  'venv',
  'env',
  '__pycache__',
  '.idea',
  '.vscode',
  '.fnix',
  '.fnix_cache',
  'coverage',
  '.angular',
  '.svelte-kit',
  '.gradle',
  '.maven',
  '.terraform',
]);

const MAX_MENTION_ITEMS = 8;
const MAX_QUERY_LEN = 80;

function pathSeparator(parent: string): string {
  return parent.includes('\\') && !parent.includes('/') ? '\\' : '/';
}

function joinPath(parent: string, name: string): string {
  const sep = pathSeparator(parent);
  return parent.endsWith(sep) ? parent + name : parent + sep + name;
}

function relativePath(projectPath: string, fullPath: string): string {
  if (!fullPath.startsWith(projectPath)) return fullPath;
  let rel = fullPath.slice(projectPath.length);
  while (rel.startsWith('\\') || rel.startsWith('/')) rel = rel.slice(1);
  return rel || fullPath;
}

/**
 * 检测光标位置前最后一个 `@` 触发的补全查询。
 * 规则：从光标往前找到第一个 `@`，且该 `@` 前要么是行首、要么是空白；
 * `@` 后到光标之间不得包含空白字符。
 */
function detectMention(value: string, cursor: number): MentionTrigger | null {
  if (cursor <= 0) return null;
  let i = cursor - 1;
  while (i >= 0) {
    const ch = value[i]!;
    if (ch === '@') {
      const before = i > 0 ? value[i - 1]! : ' ';
      const atLineStart = i === 0;
      const validBefore = atLineStart || /\s/.test(before);
      if (!validBefore) return null;
      // 从 @ 之后到 cursor 之间不能有空白
      let end = i + 1;
      while (end < cursor && !/\s/.test(value[end]!)) end++;
      if (end !== cursor) return null;
      const query = value.slice(i + 1, end);
      if (query.length > MAX_QUERY_LEN) return null;
      return { range: { at: i, start: i + 1, end }, query };
    }
    if (/\s/.test(ch)) return null;
    i--;
  }
  return null;
}

/**
 * 读取项目文件列表，最多深入两层（顶层 + 一层子目录）。
 * 浏览器 dev 模式下会抛错，由调用方显示提示。
 */
async function listProjectFiles(projectPath: string): Promise<MentionItem[]> {
  const { readDir } = await import('@tauri-apps/plugin-fs');
  const result: MentionItem[] = [];

  const walk = async (dir: string, depth: number): Promise<void> => {
    if (depth > 1) return;
    let entries;
    try {
      entries = await readDir(dir);
    } catch {
      return;
    }
    for (const entry of entries) {
      const fullPath = joinPath(dir, entry.name);
      const relPath = relativePath(projectPath, fullPath);
      if (!entry.isDirectory) {
        result.push({ name: entry.name, path: fullPath, isDir: false, relPath });
      } else {
        if (depth === 0) {
          result.push({ name: entry.name, path: fullPath, isDir: true, relPath });
        }
        if (!IGNORE_DIRS.has(entry.name.toLowerCase())) {
          await walk(fullPath, depth + 1);
        }
      }
    }
  };

  await walk(projectPath, 0);
  return result;
}

function filterItems(items: MentionItem[], query: string): MentionItem[] {
  const q = query.trim().toLowerCase();
  if (!q) {
    // No query: prefer files over directories, then alphabetical.
    return [...items]
      .sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? 1 : -1;
        return a.relPath.localeCompare(b.relPath);
      })
      .slice(0, MAX_MENTION_ITEMS);
  }
  const matched = items.filter((it) => {
    return it.name.toLowerCase().includes(q) || it.relPath.toLowerCase().includes(q);
  });
  // Prefer name matches over path-only matches, files over dirs.
  matched.sort((a, b) => {
    const an = a.name.toLowerCase().includes(q) ? 0 : 1;
    const bn = b.name.toLowerCase().includes(q) ? 0 : 1;
    if (an !== bn) return an - bn;
    if (a.isDir !== b.isDir) return a.isDir ? 1 : -1;
    return a.relPath.localeCompare(b.relPath);
  });
  return matched.slice(0, MAX_MENTION_ITEMS);
}

export function Composer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  placeholder = '输入你的问题…',
  autoFocus,
  compact,
  modelSlot,
  leftExtraSlot,
  attachments,
  onPickFiles,
  onRemoveAttachment,
  onPickFolder,
  projectPath,
  projectLabel,
  sendDisabled,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [mentionOpen, setMentionOpen] = useState(false);
  const [mentionRange, setMentionRange] = useState<MentionRange | null>(null);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionItems, setMentionItems] = useState<MentionItem[]>([]);
  const [mentionActive, setMentionActive] = useState(0);
  const [mentionLoading, setMentionLoading] = useState(false);
  const [mentionError, setMentionError] = useState<string | null>(null);
  const filesCacheRef = useRef<MentionItem[] | null>(null);
  const lastProjectRef = useRef<string>('');

  const getCursor = useCallback((): number => {
    const ta = wrapRef.current?.querySelector<HTMLTextAreaElement>('textarea');
    return ta ? (ta.selectionStart ?? value.length) : value.length;
  }, [value.length]);

  /** Detect @ trigger whenever value changes. */
  useEffect(() => {
    const cursor = getCursor();
    const trigger = detectMention(value, cursor);
    if (trigger && projectPath) {
      setMentionRange(trigger.range);
      setMentionQuery(trigger.query);
      if (!mentionOpen) setMentionOpen(true);
    } else if (mentionOpen) {
      setMentionOpen(false);
      setMentionRange(null);
      setMentionQuery('');
      setMentionItems([]);
      setMentionActive(0);
      // 清空 mentionError：否则一旦设置过错误（如"桌面环境支持 @file 补全"），
      // 即使切换环境或重新打开 popover，L293 的 effect 仍因 mentionError 非空而 setMentionItems([])，
      // 用户始终看到错误提示，无法消除
      setMentionError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, projectPath]);

  /** Reset cache when project changes. */
  useEffect(() => {
    if (lastProjectRef.current && lastProjectRef.current !== projectPath) {
      filesCacheRef.current = null;
    }
    lastProjectRef.current = projectPath || '';
  }, [projectPath]);

  /** Load files when mention opens (one-shot per project). */
  useEffect(() => {
    if (!mentionOpen) return;
    if (!projectPath) {
      setMentionError('请先打开一个项目文件夹');
      setMentionItems([]);
      return;
    }
    if (!isTauriDesktop()) {
      setMentionError('桌面环境支持 @file 补全');
      setMentionItems([]);
      return;
    }
    if (filesCacheRef.current) {
      return;
    }
    setMentionLoading(true);
    setMentionError(null);
    let cancelled = false;
    listProjectFiles(projectPath)
      .then((items) => {
        if (cancelled) return;
        filesCacheRef.current = items;
        setMentionLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setMentionError('读取文件列表失败');
        setMentionLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [mentionOpen, projectPath]);

  /** Recompute filtered items when query or cache changes. */
  useEffect(() => {
    if (!mentionOpen) return;
    const cache = filesCacheRef.current;
    if (!cache || mentionLoading || mentionError) {
      setMentionItems([]);
      return;
    }
    setMentionItems(filterItems(cache, mentionQuery));
    setMentionActive(0);
  }, [mentionOpen, mentionQuery, mentionLoading, mentionError]);

  const closeMention = useCallback(() => {
    setMentionOpen(false);
    setMentionRange(null);
    setMentionQuery('');
    setMentionItems([]);
    setMentionActive(0);
    // 同步清空 mentionError（与 detectMention 关闭分支保持一致）
    setMentionError(null);
  }, []);

  const selectMention = useCallback(
    (item: MentionItem) => {
      if (!mentionRange) return;
      const insert = `@${item.relPath} `;
      const before = value.slice(0, mentionRange.at);
      const after = value.slice(mentionRange.end);
      const next = before + insert + after;
      const newCursor = before.length + insert.length;
      onChange(next);
      closeMention();
      // Restore focus + cursor after React updates the textarea.
      requestAnimationFrame(() => {
        const ta = wrapRef.current?.querySelector<HTMLTextAreaElement>('textarea');
        if (ta) {
          ta.focus();
          ta.selectionStart = newCursor;
          ta.selectionEnd = newCursor;
        }
      });
    },
    [mentionRange, value, onChange, closeMention],
  );

  /** Intercept ArrowUp/Down/Enter/Esc while the popover is open. */
  const onKeyDownCapture = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (!mentionOpen) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        e.stopPropagation();
        setMentionActive((i) => (mentionItems.length === 0 ? 0 : (i + 1) % mentionItems.length));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        e.stopPropagation();
        setMentionActive((i) =>
          mentionItems.length === 0 ? 0 : (i - 1 + mentionItems.length) % mentionItems.length,
        );
      } else if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        e.stopPropagation();
        if (mentionItems.length > 0) {
          const idx = Math.min(mentionActive, mentionItems.length - 1);
          const item = mentionItems[idx]!;
          selectMention(item);
        } else {
          closeMention();
        }
      } else if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        closeMention();
      }
    },
    [mentionOpen, mentionItems, mentionActive, selectMention, closeMention],
  );

  const popover = useMemo(() => {
    if (!mentionOpen) return null;
    let body: ReactNode;
    if (mentionError) {
      body = <div className="fnix-mention-empty">{mentionError}</div>;
    } else if (mentionLoading) {
      body = <div className="fnix-mention-empty">加载文件列表…</div>;
    } else if (mentionItems.length === 0) {
      body = <div className="fnix-mention-empty">无匹配文件</div>;
    } else {
      body = mentionItems.map((it, i) => (
        <button
          key={it.path}
          type="button"
          role="option"
          aria-selected={i === mentionActive}
          className={`fnix-mention-item${i === mentionActive ? ' active' : ''}`}
          onMouseEnter={() => setMentionActive(i)}
          onMouseDown={(e) => {
            e.preventDefault();
            selectMention(it);
          }}
          title={it.path}
        >
          <span className="fnix-mention-name">{it.name}</span>
          <span className="fnix-mention-rel">{it.relPath}</span>
        </button>
      ));
    }
    return (
      <div className="fnix-mention-popover" role="listbox" aria-label="文件补全">
        {body}
      </div>
    );
  }, [mentionOpen, mentionError, mentionLoading, mentionItems, mentionActive, selectMention]);

  return (
    <div className="fnix-composer-wrap" ref={wrapRef} onKeyDownCapture={onKeyDownCapture}>
      <GlassComposer
        className="fnix-composer"
        value={value}
        onChange={onChange}
        onSend={onSend}
        onStop={onStop}
        streaming={streaming}
        placeholder={placeholder}
        autoFocus={autoFocus}
        compact={compact}
        modelSlot={modelSlot}
        attachments={attachments}
        onRemoveAttachment={onRemoveAttachment}
        sendDisabled={sendDisabled}
        leftSlot={
          <>
            <AttachMenu
              compact={compact}
              onPickFiles={onPickFiles}
              onPickFolder={onPickFolder}
              projectPath={projectPath}
              projectLabel={projectLabel}
            />
            {leftExtraSlot}
          </>
        }
      />
      {popover}
    </div>
  );
}
