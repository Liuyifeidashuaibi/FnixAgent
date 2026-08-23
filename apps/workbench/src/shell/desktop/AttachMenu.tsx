/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Composer 「+」菜单 — 上传附件入口（照片 / 文件 / 文件夹）。
 * 复用浏览器/WebView 原生 <input type=file>，在桌面端(Tauri WebView)与浏览器预览下均可工作。
 */

import { useEffect, useRef, useState } from "react";
import { FileUp, FolderOpen, Plus } from "lucide-react";
import { GlassIconButton } from "../../ui/glass";

interface Props {
  compact?: boolean;
  onPickFiles?: (files: FileList) => void;
  onPickFolder?: () => void;
}

export function AttachMenu({ compact, onPickFiles, onPickFolder }: Props) {
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
            添加文件夹
          </button>
        </div>
      )}
    </div>
  );
}
