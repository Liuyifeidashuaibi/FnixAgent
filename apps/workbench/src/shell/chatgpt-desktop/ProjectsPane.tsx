/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * ChatGPT-style Projects views — library + local project home (folder-backed).
 */

import { useEffect, useRef, useState } from "react";
import { FolderGit2, FolderOpen, FolderPlus, MessageSquarePlus, Pencil } from "lucide-react";
import type { RecentProject } from "../../utils/tauri";
import type { ChatThread } from "./useChatFlow";

function basename(path: string) {
  const p = path.replace(/[/\\]+$/, "");
  const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\"));
  return i >= 0 ? p.slice(i + 1) : p || path;
}

export function projectDisplayName(p: Pick<RecentProject, "path" | "alias"> | string) {
  if (typeof p === "string") return basename(p);
  return (p.alias || "").trim() || basename(p.path);
}

function formatOpened(ts?: number) {
  if (!ts) return "";
  try {
    return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

interface LibraryProps {
  projects: RecentProject[];
  onOpenFolder: () => void;
  onSelect: (path: string) => void;
  onRename?: (path: string, alias: string) => void;
}

/** Full-page Projects library (like ChatGPT Projects). */
export function ProjectsLibrary({ projects, onOpenFolder, onSelect, onRename }: LibraryProps) {
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editingPath) inputRef.current?.focus();
  }, [editingPath]);

  const commitRename = (path: string) => {
    onRename?.(path, draft.trim());
    setEditingPath(null);
  };

  return (
    <div className="oai-proj-page">
      <header className="oai-proj-page-h">
        <div>
          <h1>Projects</h1>
          <p>Local folders — shared by Work and Code.</p>
        </div>
        <button type="button" className="oai-primary" onClick={onOpenFolder}>
          <FolderPlus size={16} />
          New project
        </button>
      </header>

      <button type="button" className="oai-proj-cta" onClick={onOpenFolder}>
        <span className="oai-proj-cta-ico">
          <FolderOpen size={22} />
        </span>
        <span>
          <b>Open a local folder</b>
          <span>Connect a directory so chats can use its files</span>
        </span>
      </button>

      {projects.length > 0 ? (
        <div className="oai-proj-grid">
          {projects.map((p) => (
            <div key={p.path} className="oai-proj-card-wrap">
              {editingPath === p.path ? (
                <div className="oai-proj-card oai-proj-card-edit">
                  <span className="oai-proj-card-ico">
                    <FolderGit2 size={18} />
                  </span>
                  <input
                    ref={inputRef}
                    className="oai-proj-rename"
                    value={draft}
                    aria-label="重命名项目"
                    placeholder={basename(p.path)}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename(p.path);
                      if (e.key === "Escape") setEditingPath(null);
                    }}
                    onBlur={() => commitRename(p.path)}
                  />
                  <span className="path">{p.path}</span>
                </div>
              ) : (
                <button
                  type="button"
                  className="oai-proj-card"
                  onClick={() => onSelect(p.path)}
                >
                  <span className="oai-proj-card-ico">
                    <FolderGit2 size={18} />
                  </span>
                  <b>{projectDisplayName(p)}</b>
                  <span className="path">{p.path}</span>
                  {p.openedAt ? <span className="when">{formatOpened(p.openedAt)}</span> : null}
                </button>
              )}
              {onRename && editingPath !== p.path ? (
                <button
                  type="button"
                  className="oai-proj-rename-btn"
                  title="重命名显示名"
                  aria-label="重命名项目"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDraft(p.alias || basename(p.path));
                    setEditingPath(p.path);
                  }}
                >
                  <Pencil size={12} />
                </button>
              ) : null}
            </div>
          ))}
        </div>
      ) : (
        <div className="oai-proj-empty">还没有本地项目。打开一个文件夹即可创建。</div>
      )}
    </div>
  );
}

interface HomeProps {
  path: string;
  displayName?: string;
  threads: ChatThread[];
  activeId: string | null;
  onNewChat: () => void;
  onOpenThread: (id: string) => void;
  onChangeFolder: () => void;
  onOpenCodex: () => void;
  onRename?: (alias: string) => void;
}

/** Single local project home. */
export function ProjectHome({
  path,
  displayName,
  threads,
  activeId,
  onNewChat,
  onOpenThread,
  onChangeFolder,
  onOpenCodex,
  onRename,
}: HomeProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayName || basename(path));
  const inputRef = useRef<HTMLInputElement>(null);
  const title = displayName || basename(path);

  useEffect(() => {
    setDraft(displayName || basename(path));
  }, [displayName, path]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  return (
    <div className="oai-proj-page oai-proj-home">
      <div className="oai-proj-hero">
        <span className="oai-proj-hero-ico">
          <FolderGit2 size={28} />
        </span>
        <div className="oai-proj-hero-meta">
          {editing && onRename ? (
            <input
              ref={inputRef}
              className="oai-proj-rename hero"
              value={draft}
              aria-label="重命名项目"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  onRename(draft.trim());
                  setEditing(false);
                }
                if (e.key === "Escape") setEditing(false);
              }}
              onBlur={() => {
                onRename(draft.trim());
                setEditing(false);
              }}
            />
          ) : (
            <h1>
              {title}
              {onRename ? (
                <button
                  type="button"
                  className="oai-proj-rename-btn inline"
                  title="重命名显示名"
                  aria-label="重命名项目"
                  onClick={() => {
                    setDraft(title);
                    setEditing(true);
                  }}
                >
                  <Pencil size={14} />
                </button>
              ) : null}
            </h1>
          )}
          <span className="oai-proj-badge">本地文件夹</span>
          <p title={path}>{path}</p>
        </div>
      </div>

      <div className="oai-proj-actions">
        <button type="button" className="oai-primary" onClick={onNewChat}>
          <MessageSquarePlus size={16} />
          New chat
        </button>
        <button type="button" className="oai-secondary" onClick={onOpenCodex}>
          Open in Code
        </button>
        <button type="button" className="oai-secondary" onClick={onChangeFolder}>
          <FolderOpen size={15} />
          Change folder
        </button>
      </div>

      <div className="oai-proj-chats">
        <div className="oai-proj-chats-h">Chats in this project</div>
        {threads.length === 0 ? (
          <div className="oai-proj-empty">No chats yet. Start one to keep work with this folder.</div>
        ) : (
          <div className="oai-proj-chat-list">
            {threads.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`oai-proj-chat-row${activeId === t.id ? " on" : ""}`}
                onClick={() => onOpenThread(t.id)}
              >
                <b>{t.title}</b>
                <span>{formatOpened(t.updatedAt)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
