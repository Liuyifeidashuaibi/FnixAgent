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
    <div className="fnix-bench-root" role="dialog" aria-label="全链路基准测试">
      <header className="fnix-bench-head">
        <div>
          <h1>全链路测试</h1>
          <p>前端 · 后台引擎 · 运行环境 · Work · Code · FCS</p>
        </div>
        <button type="button" className="fnix-ibtn" onClick={onClose} aria-label="Close">
          <X size={18} />
        </button>
      </header>

      <div className="fnix-bench-toolbar">
        <label className="fnix-bench-check">
          <input
            type="checkbox"
            checked={includeLlm}
            disabled={running}
            onChange={(e) => setIncludeLlm(e.target.checked)}
          />
          含 LLM + Code 冒烟（较慢，需 API Key）
        </label>
        <button type="button" className="fnix-bench-run" disabled={running} onClick={() => void run()}>
          {running ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
          {running ? "运行中…" : "开始测试"}
        </button>
      </div>

      {overall !== null && (
        <div className={`fnix-bench-score ${scoreColor(overall)}`}>
          <span className="fnix-bench-score-num">{overall}</span>
          <span className="fnix-bench-score-label">
            系统分 {report?.hard_pass ? "· PASS" : "· 需优化"}
            {report?.fcs != null ? ` · FCS ${report.fcs}` : ""}
          </span>
        </div>
      )}

      {error && <div className="fnix-bench-error">{error}</div>}

      <div className="fnix-bench-stages">
        {stages.length === 0 && !running && (
          <p className="fnix-bench-empty">
            在 Composer 输入 <code>/benchmark</code> 或点「开始测试」验证整个项目链路。
          </p>
        )}
        {stages.map((s) => (
          <div key={s.id} className={`fnix-bench-row ${s.ok ? "ok" : "bad"}`}>
            {s.ok ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
            <div className="fnix-bench-row-body">
              <span className="fnix-bench-row-id">{s.id}</span>
              <span className="fnix-bench-row-msg">{s.message}</span>
            </div>
            <span className="fnix-bench-row-meta">{Math.round(s.duration_ms)}ms</span>
          </div>
        ))}
        {running && (
          <div className="fnix-bench-row pending">
            <Activity size={16} className="spin" />
            <span>执行下一阶段…</span>
          </div>
        )}
      </div>

      {report && report.recommendations.length > 0 && (
        <section className="fnix-bench-recs">
          <h3>优化建议</h3>
          <ul>
            {report.recommendations.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
      )}

      {report && Object.keys(report.by_category).length > 0 && (
        <section className="fnix-bench-cats">
          <h3>分维度</h3>
          <div className="fnix-bench-cat-grid">
            {Object.entries(report.by_category).map(([cat, score]) => (
              <div key={cat} className={`fnix-bench-cat ${scoreColor(score)}`}>
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
