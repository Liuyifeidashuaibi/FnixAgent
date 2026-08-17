/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Full-chain benchmark panel — run from Settings or composer `/benchmark`.
 */

import { useCallback, useRef, useState } from "react";
import { Activity, CheckCircle2, Loader2, Play, X, XCircle } from "lucide-react";
import {
  runFullChainBenchmark,
  scoreColor,
  type BenchmarkReport,
  type BenchmarkStage,
} from "../../services/benchmark/fullChainBenchmark";

interface Props {
  workspace?: string;
  onClose: () => void;
}

export function FullChainBenchmarkPanel({ workspace, onClose }: Props) {
  const [running, setRunning] = useState(false);
  const [includeLlm, setIncludeLlm] = useState(false);
  const [stages, setStages] = useState<BenchmarkStage[]>([]);
  const [report, setReport] = useState<BenchmarkReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    setRunning(true);
    setError(null);
    setReport(null);
    setStages([]);

    try {
      const result = await runFullChainBenchmark({
        workspace,
        includeLlm,
        fcsLimit: 3,
        fcsTag: "smoke",
        signal: ac.signal,
        onStage: (s) => setStages((prev) => [...prev.filter((x) => x.id !== s.id), s]),
      });
      setReport(result);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setError(String(e));
      }
    } finally {
      setRunning(false);
    }
  }, [workspace, includeLlm]);

  const overall = report?.overall_score ?? null;

  return (
    <div className="oai-bench-root" role="dialog" aria-label="全链路基准测试">
      <header className="oai-bench-head">
        <div>
          <h1>全链路测试</h1>
          <p>前端 · agentd · Harness · Work · Code · FCS</p>
        </div>
        <button type="button" className="oai-ibtn" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </header>

      <div className="oai-bench-toolbar">
        <label className="oai-bench-check">
          <input
            type="checkbox"
            checked={includeLlm}
            disabled={running}
            onChange={(e) => setIncludeLlm(e.target.checked)}
          />
          含 LLM + Code 冒烟（较慢，需 API Key）
        </label>
        <button type="button" className="oai-bench-run" disabled={running} onClick={() => void run()}>
          {running ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {running ? "运行中…" : "开始测试"}
        </button>
      </div>

      {overall !== null && (
        <div className={`oai-bench-score ${scoreColor(overall)}`}>
          <span className="oai-bench-score-num">{overall}</span>
          <span className="oai-bench-score-label">
            系统分 {report?.hard_pass ? "· PASS" : "· 需优化"}
            {report?.fcs != null ? ` · FCS ${report.fcs}` : ""}
          </span>
        </div>
      )}

      {error && <div className="oai-bench-error">{error}</div>}

      <div className="oai-bench-stages">
        {stages.length === 0 && !running && (
          <p className="oai-bench-empty">
            在 Composer 输入 <code>/benchmark</code> 或点「开始测试」验证整个项目链路。
          </p>
        )}
        {stages.map((s) => (
          <div key={s.id} className={`oai-bench-row ${s.ok ? "ok" : "bad"}`}>
            {s.ok ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
            <div className="oai-bench-row-body">
              <span className="oai-bench-row-id">{s.id}</span>
              <span className="oai-bench-row-msg">{s.message}</span>
            </div>
            <span className="oai-bench-row-meta">{Math.round(s.duration_ms)}ms</span>
          </div>
        ))}
        {running && (
          <div className="oai-bench-row pending">
            <Activity size={16} className="spin" />
            <span>执行下一阶段…</span>
          </div>
        )}
      </div>

      {report && report.recommendations.length > 0 && (
        <section className="oai-bench-recs">
          <h3>优化建议</h3>
          <ul>
            {report.recommendations.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      {report && Object.keys(report.by_category).length > 0 && (
        <section className="oai-bench-cats">
          <h3>分维度</h3>
          <div className="oai-bench-cat-grid">
            {Object.entries(report.by_category).map(([cat, score]) => (
              <div key={cat} className={`oai-bench-cat ${scoreColor(score)}`}>
                <span>{cat}</span>
                <b>{score}</b>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
