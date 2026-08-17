/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Work artifact quality / version / source — Results panel contract.
 */

export type ArtifactQuality = "ready" | "check" | "unknown";
export type ArtifactSource = "work_stream" | "craft" | "import";

const READY_EXT = new Set([
  "html",
  "htm",
  "md",
  "txt",
  "csv",
  "json",
  "docx",
  "xlsx",
  "pptx",
  "pdf",
  "png",
  "jpg",
  "jpeg",
  "svg",
  "css",
  "js",
  "ts",
]);

const OFFICE_EXT = new Set(["docx", "xlsx", "pptx", "pdf"]);

export function extOfPath(path: string): string {
  const b = path.replace(/[/\\]+$/, "").split(/[/\\]/).pop() || "";
  const i = b.lastIndexOf(".");
  return i >= 0 ? b.slice(i + 1).toLowerCase() : "";
}

export function assessArtifactQuality(path: string): ArtifactQuality {
  const ext = extOfPath(path);
  if (!ext) return "unknown";
  if (READY_EXT.has(ext)) return "ready";
  return "check";
}

export function qualityLabel(q: ArtifactQuality): string {
  if (q === "ready") return "可打开";
  if (q === "check") return "需核对";
  return "未知";
}

export function isOfficeArtifact(path: string): boolean {
  return OFFICE_EXT.has(extOfPath(path));
}

/** Match mission expected_deliverables against produced paths (0–1). */
export function deliverableCoverage(
  artifacts: { path: string }[],
  expected: unknown,
): number | null {
  if (!Array.isArray(expected) || expected.length === 0) return null;
  const paths = artifacts.map((a) => a.path.toLowerCase().replace(/\\/g, "/"));
  let hit = 0;
  for (const raw of expected) {
    const hint = String(raw || "")
      .toLowerCase()
      .replace(/\\/g, "/")
      .trim();
    if (!hint) continue;
    if (paths.some((p) => p.includes(hint) || hint.includes(extOfPath(p)))) {
      hit += 1;
    }
  }
  return Math.round((100 * hit) / expected.length);
}

export function formatArtifactVersion(ts: number | undefined, now = Date.now()): string {
  if (!ts) return "v1";
  const sec = Math.max(0, Math.floor((now - ts) / 1000));
  if (sec < 60) return `v1 · just now`;
  if (sec < 3600) return `v1 · ${Math.floor(sec / 60)}m`;
  return `v1 · ${new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}
