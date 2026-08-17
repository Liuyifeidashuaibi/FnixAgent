/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Code Review risk / conflict heuristics for chatgpt-desktop ReviewPane.
 */

import { hasConflictMarkers } from "../../utils/conflictParser";
import type { CodexFileChange } from "./fnixRuntime";

export type ReviewRiskLevel = "low" | "medium" | "high";

export type FileReviewRisk = {
  path: string;
  level: ReviewRiskLevel;
  score: number;
  reasons: string[];
  hasConflict: boolean;
};

const SENSITIVE =
  /(^|[/\\])(\.env|secrets?|credentials?|id_rsa|\.pem|\.key|password)([/\\.]|$)/i;
const DELETE_HINT = /delete|unlink|remove/i;

function diffStats(diff?: string): { add: number; del: number; lines: number } {
  const text = diff || "";
  const lines = text.split("\n");
  let add = 0;
  let del = 0;
  for (const l of lines) {
    if (l.startsWith("+") && !l.startsWith("+++")) add += 1;
    else if (l.startsWith("-") && !l.startsWith("---")) del += 1;
  }
  return { add, del, lines: lines.length };
}

export function assessFileReviewRisk(change: CodexFileChange): FileReviewRisk {
  const reasons: string[] = [];
  let score = 0;
  const body = change.content || change.diff || "";
  const hasConflict = hasConflictMarkers(body);
  if (hasConflict) {
    score += 60;
    reasons.push("conflict markers");
  }

  const action = (change.action || "").toLowerCase();
  if (action.includes("delete") || DELETE_HINT.test(action)) {
    score += 40;
    reasons.push("delete");
  }
  if (SENSITIVE.test(change.path || "")) {
    score += 55;
    reasons.push("sensitive path");
  }

  const stats = diffStats(change.diff);
  if (stats.add + stats.del >= 200 || stats.lines >= 400) {
    score += 25;
    reasons.push("large diff");
  } else if (stats.add + stats.del >= 80) {
    score += 12;
    reasons.push("medium diff");
  }

  if (!change.content && !change.diff) {
    score += 8;
    reasons.push("no preview body");
  }

  const level: ReviewRiskLevel = score >= 50 ? "high" : score >= 20 ? "medium" : "low";
  return {
    path: change.path,
    level,
    score,
    reasons: reasons.length ? reasons : ["routine edit"],
    hasConflict,
  };
}

export function assessReviewBatch(changes: CodexFileChange[]): {
  files: FileReviewRisk[];
  maxLevel: ReviewRiskLevel;
  conflictCount: number;
} {
  const files = changes.map(assessFileReviewRisk);
  const conflictCount = files.filter((f) => f.hasConflict).length;
  const maxLevel = files.some((f) => f.level === "high")
    ? "high"
    : files.some((f) => f.level === "medium")
      ? "medium"
      : "low";
  return { files, maxLevel, conflictCount };
}
