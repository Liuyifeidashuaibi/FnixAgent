/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Desktop-only helpers for Work Results (open artifact / folder).
 */

import { isTauriDesktop } from "./desktopEnv";

/**
 * 拼接 workspace 与相对路径生成绝对路径。
 * - 若 full 已是绝对路径（Windows 盘符开头）则原样返回
 * - 否则按 workspace 中存在的分隔符（\ 或 /）拼接，去除首尾冗余分隔符
 * 原 openArtifactPath / revealArtifactFolder 各自重复了这 ~5 行逻辑，抽取为 helper。
 */
function resolveArtifactPath(artifactPath: string, workspace: string): string | null {
  const full = artifactPath.trim();
  if (!full) return null;
  const ws = (workspace || "").trim();
  if (/^[a-zA-Z]:[/\\]/.test(full) || !ws) return full;
  const sep = ws.includes("\\") ? "\\" : "/";
  return `${ws.replace(/[/\\]+$/, "")}${sep}${full.replace(/^[/\\]+/, "")}`;
}

export async function openArtifactPath(artifactPath: string, workspace: string): Promise<boolean> {
  if (!isTauriDesktop()) return false;
  const full = resolveArtifactPath(artifactPath, workspace);
  if (!full) return false;
  try {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(full);
    return true;
  } catch {
    return false;
  }
}

export async function revealArtifactFolder(artifactPath: string, workspace: string): Promise<boolean> {
  if (!isTauriDesktop()) return false;
  const full = resolveArtifactPath(artifactPath, workspace);
  if (!full) return false;
  const dir = full.replace(/[/\\][^/\\]+$/, "");
  try {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(dir || full);
    return true;
  } catch {
    return false;
  }
}
