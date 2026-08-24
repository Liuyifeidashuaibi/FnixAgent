/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code is proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Composer 「+」菜单 — 上传附件 + 选择/切换工作区文件夹，统一入口。
 * 复用浏览器/WebView 原生 <input type=file>，在桌面端(Tauri WebView)与浏览器预览下均可工作。
 *
 * 工作区列表：用户通过"+"添加但未发消息的 workspace 只出现在这里，
 * 不出现在左侧任务栏。发送消息后 workspace 才进入左侧任务栏。
 */

import { useEffect, useRef, useState } from "react";
import { FileUp, FolderOpen, Plus, Check, Layers } from "lucide-react";
import { GlassIconButton } from "../../ui/glass";
import { projectDisplayName } from "./ProjectsPane";
import type { RecentProject } from "../../utils/tauri";

interface Props {
  compact?: boolean;
  onPickFiles?: (files: FileList) => void;
  onPickFolder?: () => void;
  /** 当前工作区路径 */
  projectPath?: string;
  /** 当前工作区显示名 */
  projectLabel?: string;
  /** 最近打开的工作区列表（用于下拉切换） */
  recentProjects?: RecentProject[];
  /** 切换到指定工作区 */
  onSwitchWorkspace?: (path: string) => void;
}

export function AttachMenu({
  compact,
  onPickFiles,
  onPickFolder,
  projectPath,
  projectLabel,
  recentProjects,
  onSwitchWorkspace,
}: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);

  const chooseFiles = () => {
    setOpen(false);
    fileInputRef.current?.click();
  };

  // 除了当前 projectPath 之外的其他 workspace（最多 8 个）
  const otherWorkspaces = (recentProjects || [])
    .filter((p) => p.path !== projectPath)
    .slice(0, 8);

  return (
    <div className="fnix-attach" ref={ref}>
      <GlassIconButton
        round
        title="添加附件或选择文件夹"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Plus size={compact ? 16 : 18} />
      </GlassIconButton>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,*/*"
        className="fnix-attach-input"
        onChange={(e) => {
          if (e.target.files && e.target.files.length > 0) {
            onPickFiles?.(e.target.files);
          }
          e.target.value = "";
        }}
      />
      {open && (
        <div className="fnix-attach-menu" role="menu">
          <button type="button" role="menuitem" onClick={chooseFiles}>
            <FileUp size={15} />
            上传附件（照片 / 文件）
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onPickFolder?.();
            }}
          >
            <FolderOpen size={15} />
            <span className="fnix-attach-ws-label">
              {projectPath ? projectLabel || projectPath : "选择工作区文件夹"}
            </span>
            {projectPath ? (
              <Check size={13} className="fnix-attach-ws-check" />
            ) : null}
          </button>

          {/* 工作区切换列表 */}
          {otherWorkspaces.length > 0 && (
            <>
              <div className="fnix-attach-divider" role="separator" />
              <div className="fnix-attach-ws-list" role="group" aria-label="切换工作区">
                {otherWorkspaces.map((p) => (
                  <button
                    key={p.path}
                    type="button"
                    role="menuitem"
                    className="fnix-attach-ws-item"
                    title={p.path}
                    onClick={() => {
                      setOpen(false);
                      onSwitchWorkspace?.(p.path);
                    }}
                  >
                    <Layers size={13} />
                    <span className="fnix-attach-ws-name">
                      {projectDisplayName(p)}
                    </span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
