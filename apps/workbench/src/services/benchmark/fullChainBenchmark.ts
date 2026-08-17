/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Full-chain system benchmark — frontend + backend orchestration.
 * POST /api/v1/benchmark/run (NDJSON stream)
 */

import { getFnixApiBase, loadHarnessConfig, pingAgentd } from "../../lib/fnixBridge";

export type BenchmarkStage = {
  id: string;
  category: string;
  ok: boolean;
  score: number;
  message: string;
  duration_ms: number;
  details?: Record<string, unknown>;
};

export type BenchmarkReport = {
  overall_score: number;
  hard_pass: boolean;
  stage_count: number;
  passed: number;
  by_category: Record<string, number>;
  fcs?: number | null;
  recommendations: string[];
  stages: BenchmarkStage[];
};

export type BenchmarkRunOptions = {
  workspace?: string;
  includeLlm?: boolean;
  fcsLimit?: number;
  fcsTag?: string;
  signal?: AbortSignal;
  onStage?: (stage: BenchmarkStage) => void;
};

const BENCHMARK_TRIGGERS = [
  /^\/benchmark\b/i,
  /^\/全链路\b/,
  /^全链路测试/,
  /^运行全链路/,
  /^run full.?chain/i,
  /^system (test|benchmark)/i,
];

export function isBenchmarkPrompt(text: string): boolean {
  const t = text.trim();
  return BENCHMARK_TRIGGERS.some((re) => re.test(t));
}

async function runClientProbes(): Promise<BenchmarkStage[]> {
  const stages: BenchmarkStage[] = [];
  const t0 = performance.now();

  const pingOk = await pingAgentd();
  stages.push({
    id: "frontend.ping",
    category: "frontend",
    ok: pingOk,
    score: pingOk ? 100 : 0,
    message: pingOk ? `agentd reachable at ${getFnixApiBase()}` : "agentd unreachable",
    duration_ms: Math.round(performance.now() - t0),
    details: { api_base: getFnixApiBase() },
  });

  const t1 = performance.now();
  const cfg = await loadHarnessConfig();
  const cfgOk = cfg !== null;
  stages.push({
    id: "frontend.harness",
    category: "frontend",
    ok: cfgOk,
    score: cfgOk ? 100 : 0,
    message: cfgOk
      ? `harness config · ${cfg?.provider || "?"} / ${cfg?.model || "?"}`
      : "harness config fetch failed",
    duration_ms: Math.round(performance.now() - t1),
    details: cfg ? { has_api_key: cfg.has_api_key, model: cfg.model } : {},
  });

  return stages;
}

async function readBenchmarkStream(
  res: Response,
  signal: AbortSignal | undefined,
  onStage?: (stage: BenchmarkStage) => void,
): Promise<BenchmarkReport> {
  if (!res.body) throw new Error("empty response body");
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let report: BenchmarkReport | null = null;

  while (true) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    while (buf.includes("\n")) {
      const i = buf.indexOf("\n");
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (!line) continue;
      const ev = JSON.parse(line) as {
        type: string;
        stage?: BenchmarkStage;
        report?: BenchmarkReport;
      };
      if (ev.type === "stage" && ev.stage) {
        onStage?.(ev.stage);
      } else if (ev.type === "done" && ev.report) {
        report = ev.report;
      }
    }
  }

  if (!report) throw new Error("benchmark stream ended without report");
  return report;
}

export async function runFullChainBenchmark(opts: BenchmarkRunOptions = {}): Promise<BenchmarkReport> {
  const clientStages = await runClientProbes();
  for (const s of clientStages) opts.onStage?.(s);

  const res = await fetch(`${getFnixApiBase()}/api/v1/benchmark/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace: opts.workspace || undefined,
      include_llm: opts.includeLlm ?? false,
      fcs_limit: opts.fcsLimit ?? 3,
      fcs_tag: opts.fcsTag ?? "smoke",
      agent_base: getFnixApiBase(),
      client_stages: clientStages,
    }),
    signal: opts.signal,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`benchmark HTTP ${res.status}: ${text.slice(0, 200)}`);
  }

  return readBenchmarkStream(res, opts.signal, opts.onStage);
}

export function scoreColor(score: number): string {
  if (score >= 85) return "ok";
  if (score >= 60) return "warn";
  return "bad";
}
