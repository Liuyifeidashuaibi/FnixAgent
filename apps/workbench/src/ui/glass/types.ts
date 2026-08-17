/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** Shared activity model for GlassProcessList (compatible with shell activityTypes). */

export type GlassActivityKind =
  | "plan"
  | "think"
  | "tool"
  | "read"
  | "edit"
  | "write"
  | "test"
  | "run"
  | "mission"
  | "done"
  | "error";

export type GlassActivityStatus = "running" | "done" | "error" | "needs_input";

export interface GlassActivityItem {
  id: string;
  kind: GlassActivityKind;
  title: string;
  meta?: string;
  status: GlassActivityStatus;
  detail?: string;
  path?: string;
  startedAt: number;
  endedAt?: number;
}
