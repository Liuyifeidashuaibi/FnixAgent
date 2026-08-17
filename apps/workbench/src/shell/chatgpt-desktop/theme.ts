/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** Shell appearance — 支持 light/dark/system 三种偏好,显式值原样返回,system 跟随 matchMedia。 */

export type ShellThemePreference = "light" | "dark" | "system";
export type ShellThemeResolved = "light" | "dark";

/** 规范化用户原始主题偏好:仅接受 light/dark/system,其余一律回退 system。 */
export function normalizeThemePref(raw?: string | null): ShellThemePreference {
  if (raw === "light" || raw === "dark" || raw === "system") return raw;
  return "system";
}

/** 解析偏好为具体 shell 主题:显式 light/dark 原样返回,system 通过 matchMedia 推断(非浏览器环境回退 light)。 */
export function resolveShellTheme(pref?: string | null): ShellThemeResolved {
  const normalized = normalizeThemePref(pref);
  if (normalized === "light" || normalized === "dark") return normalized;
  // system:仅当浏览器环境且 matchMedia 可用时才推断,否则回退 light
  if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return "light";
}
