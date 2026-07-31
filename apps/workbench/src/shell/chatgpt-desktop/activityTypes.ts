/** ChatGPT Desktop 过程可视化 — 活动项模型（对标 tool activity / subagent progress） */

export type ActivityKind =
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

export type ActivityStatus = "running" | "done" | "error" | "cancelled" | "needs_input";

export interface ActivityItem {
  id: string;
  kind: ActivityKind;
  title: string;
  meta?: string;
  status: ActivityStatus;
  detail?: string;
  path?: string;
  startedAt: number;
  endedAt?: number;
}

export function activityId(prefix = "act"): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

/** 合并：同 path 的 edit 更新；running think/tool 被新状态替换 */
export function upsertActivity(prev: ActivityItem[], next: ActivityItem): ActivityItem[] {
  const sameId = prev.findIndex((item) => item.id === next.id);
  if (sameId >= 0) {
    const copy = [...prev];
    copy[sameId] = {
      ...copy[sameId]!,
      ...next,
      kind: next.kind === "tool" ? copy[sameId]!.kind : next.kind,
      title: next.kind === "tool" ? copy[sameId]!.title : next.title,
      startedAt: copy[sameId]!.startedAt,
      path: next.path || copy[sameId]!.path,
    };
    return copy;
  }
  if (next.status !== "running" && next.meta) {
    const i = prev.findLastIndex(
      (item) => item.status === "running" && item.meta === next.meta,
    );
    if (i >= 0) {
      const copy = [...prev];
      copy[i] = {
        ...copy[i]!,
        ...next,
        id: copy[i]!.id,
        kind: next.kind === "tool" ? copy[i]!.kind : next.kind,
        title: next.kind === "tool" ? copy[i]!.title : next.title,
        startedAt: copy[i]!.startedAt,
        path: next.path || copy[i]!.path,
      };
      return copy;
    }
  }
  if (next.path && (next.kind === "edit" || next.kind === "write" || next.kind === "read")) {
    const i = prev.findIndex((a) => a.path === next.path && a.kind === next.kind);
    if (i >= 0) {
      const copy = [...prev];
      copy[i] = { ...copy[i]!, ...next, id: copy[i]!.id };
      return copy;
    }
  }
  if (next.status === "running" && (next.kind === "think" || next.kind === "tool" || next.kind === "plan")) {
    const i = prev.findIndex((a) => a.status === "running" && a.kind === next.kind);
    if (i >= 0) {
      const copy = [...prev];
      copy[i] = { ...copy[i]!, ...next, id: copy[i]!.id, startedAt: copy[i]!.startedAt };
      return copy;
    }
  }
  return [...prev, next].slice(-40);
}

export function finishRunning(prev: ActivityItem[], status: ActivityStatus = "done"): ActivityItem[] {
  const now = Date.now();
  return prev.map((a) =>
    a.status === "running" ? { ...a, status, endedAt: a.endedAt ?? now } : a,
  );
}
