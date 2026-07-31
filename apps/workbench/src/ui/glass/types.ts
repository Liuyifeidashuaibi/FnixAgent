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
