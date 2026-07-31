/**
 * GlassProcessList — 过程时间线（Spec 2 新中式宋韵风升级）。
 *
 * 设计原则：
 *  - 留白大于装饰，线轴细而克制
 *  - 青灰 #4a6fa5 主色，竹青 #5a7a5a 表示成功，赭石 #a85751 表示错误
 *  - 思考链（kind=think + detail）默认折叠，点击展开
 *  - 工具调用（kind=tool + detail）显示参数摘要，点击展开看完整
 *  - 不用 emoji 不用图标色彩浓烈，节制感
 */

import { useState } from "react";
import {
  Check,
  CircleAlert,
  FileCode2,
  ListTodo,
  Loader2,
  Pencil,
  Sparkles,
  Terminal,
} from "lucide-react";
import type { GlassActivityItem, GlassActivityKind } from "./types";

const ICONS: Record<GlassActivityKind, typeof Check> = {
  plan: ListTodo,
  think: Sparkles,
  tool: Terminal,
  read: FileCode2,
  edit: Pencil,
  write: Pencil,
  test: Check,
  run: Terminal,
  mission: ListTodo,
  done: Check,
  error: CircleAlert,
};

export interface GlassProcessListProps {
  items: GlassActivityItem[];
  onOpenDiff?: (path: string) => void;
  compact?: boolean;
  title?: string;
}

function elapsed(a: GlassActivityItem): string | null {
  const end = a.endedAt ?? (a.status === "running" ? Date.now() : null);
  if (!end) return null;
  const s = Math.max(0, Math.floor((end - a.startedAt) / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/** 截断长文本用于预览，保留首尾可见 */
function truncate(text: string, max = 140): string {
  if (text.length <= max) return text;
  return text.slice(0, max / 2) + " … " + text.slice(-max / 2);
}

/**
 * 统一解析 activity.detail JSON。原代码 10+ 处 try/catch + JSON.parse + 字段判定重复，
 * 抽取为单个 helper：
 *   - detail 为空或非对象 → null
 *   - 缺任一 required 字段 → null
 *   - 命中任一 forbidden 字段 → null
 *   - 否则按 T 断言返回
 */
function parseCardDetail<T>(
  detail: string | undefined,
  opts: { required?: readonly string[]; forbidden?: readonly string[] } = {},
): T | null {
  if (!detail) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(detail);
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object") return null;
  const obj = parsed as Record<string, unknown>;
  if (opts.required && !opts.required.every((k) => k in obj)) return null;
  if (opts.forbidden && opts.forbidden.some((k) => k in obj)) return null;
  return obj as unknown as T;
}

export function GlassProcessList({
  items,
  onOpenDiff,
  compact,
  title = "进展",
}: GlassProcessListProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  if (!items.length) return null;

  const toggle = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <div className={`glass-process${compact ? " compact" : ""}`} aria-label="Process activity">
      <div className="glass-process-h">{title}</div>
      <ol className="glass-process-list">
        {items.map((a) => {
          const Icon = ICONS[a.kind] || Terminal;
          const time = elapsed(a);
          const hasDetail = Boolean(a.detail && a.detail.trim());
          const isOpen = Boolean(expanded[a.id]);
          const isThink = a.kind === "think";
          const isError = a.status === "error" || a.kind === "error";
          // Spec 5: DecisionCard 检测 — kind=plan 且 detail 是 decision_context JSON
          const decisionData = a.kind === "plan"
            ? parseCardDetail<{
                goal?: string;
                concepts?: { id: string; label: string; layer: string }[];
                concept_edges?: { from: string; to: string; type: string }[];
                reasoning_mode?: string;
                memory_short_count?: number;
                memory_long_count?: number;
                risks?: { type: string; between: string[] }[];
              }>(a.detail, { required: ["concepts"] })
            : null;
          const isDecisionCard = decisionData !== null;

          // Spec 6 DAAO: RouteCard 检测 — kind=plan 且 detail 有 route 字段
          const routeData = a.kind === "plan" && !isDecisionCard
            ? parseCardDetail<{
                route?: string;
                max_steps?: number;
                max_reflect_rounds?: number;
                workspace_kind?: string;
                work_mode?: string;
                reason?: string;
                tool_count?: number;
                // Spec 7+ 四维闭环新字段
                difficulty_score?: number;
                hera_hit_rate?: number;
                recent_failure_rate?: number;
                confidence?: number;
                tool_subset?: string[];
                fallback?: boolean;
              }>(a.detail, { required: ["route", "reason"] })
            : null;
          const isRouteCard = routeData !== null;

          // Spec 5: CriticVerdictCard 检测 — kind=done/think 且 detail 有 passed+score 字段
          const criticVerdictData = parseCardDetail<{
            passed?: boolean;
            score?: number;
            issues?: string[];
            suggestions?: string[];
          }>(a.detail, {
            required: ["passed", "score"],
            forbidden: ["reflection", "skill_id", "example_id"],
          });
          const isCriticVerdictCard = criticVerdictData !== null;

          // Spec 7+: ReflectionToSkillCard 检测 — kind=done 且 detail 有 saved+round+library_total
          const reflectionToSkillData = a.kind === "done"
            ? parseCardDetail<{
                saved?: boolean;
                round?: number;
                library_total?: number;
              }>(a.detail, {
                required: ["saved", "round", "library_total"],
                forbidden: ["skill_id", "example_id"],
              })
            : null;
          const isReflectionToSkillCard = reflectionToSkillData !== null;

          // 史诗级优化: GuardrailCard 检测 — detail 有 passed + (summary|missing|validation_count)
          // 注：parseCardDetail 不支持 OR 条件，因此先宽松解析再二次判定
          const guardrailData = parseCardDetail<{
            passed?: boolean;
            summary?: string;
            missing?: string[];
            issues?: string[][];
            validation_count?: number;
            repair_attempt?: boolean;
            artifacts_after?: number;
          }>(a.detail, {
            required: ["passed"],
            forbidden: ["score", "saved", "reflection"],
          });
          // 二次过滤：必须有 summary / validation_count / missing 之一
          const isGuardrailCard = guardrailData !== null
            && ("summary" in (guardrailData as Record<string, unknown>)
              || "validation_count" in (guardrailData as Record<string, unknown>)
              || "missing" in (guardrailData as Record<string, unknown>));

          // Spec 6 VMAO: ReflectionCard 检测 — kind=think 且 detail 有 reflection 字段
          const reflectionData = a.kind === "think"
            ? parseCardDetail<{
                round?: number;
                reason?: string;
                reflection?: string;
                previous_failures?: { name: string; error: string; step?: number }[];
              }>(a.detail, { required: ["reflection"] })
            : null;
          const isReflectionCard = reflectionData !== null;

          // Spec 6 HERA: SkillRetrievedCard 检测 — kind=plan 且 detail 有 skills 数组
          const skillRetrievedData = a.kind === "plan" && !isDecisionCard && !isRouteCard
            ? parseCardDetail<{
                skills?: { task_signature: string; solution_summary: string; usage_count: number; workspace_kind: string }[];
                total_in_library?: number;
              }>(a.detail, { required: ["skills"] })
            : null;
          // 二次过滤：原代码要求 Array.isArray(parsed.skills)，避免 skills 为非数组时误判
          const isSkillRetrievedCard = skillRetrievedData !== null && Array.isArray(skillRetrievedData.skills);

          // Spec 6 HERA: SkillSavedCard 检测 — kind=done 且 detail 有 skill_id 字段
          const skillSavedData = a.kind === "done"
            ? parseCardDetail<{
                skill_id?: string;
                task_signature?: string;
                saved?: boolean;
                library_total?: number;
              }>(a.detail, { required: ["skill_id"] })
            : null;
          const isSkillSavedCard = skillSavedData !== null;

          // Spec 6 Self-Optimizing: FewShotRetrievedCard 检测 — kind=plan 且 detail 有 examples 数组
          const fewShotRetrievedData = a.kind === "plan" && !isDecisionCard && !isRouteCard && !isSkillRetrievedCard
            ? parseCardDetail<{
                examples?: { task_signature: string; score: number; usage_count: number; workspace_kind: string; tool_sequence?: string[] }[];
                total_in_library?: number;
              }>(a.detail, { required: ["examples"] })
            : null;
          const isFewShotRetrievedCard = fewShotRetrievedData !== null && Array.isArray(fewShotRetrievedData.examples);

          // Spec 6 Self-Optimizing: FewShotSavedCard 检测 — kind=done 且 detail 有 example_id 字段
          const fewShotSavedData = a.kind === "done" && !isSkillSavedCard
            ? parseCardDetail<{
                example_id?: string;
                task_signature?: string;
                score?: number;
                saved?: boolean;
                library_total?: number;
              }>(a.detail, { required: ["example_id"] })
            : null;
          const isFewShotSavedCard = fewShotSavedData !== null;

          return (
            <li
              key={a.id}
              className={`glass-process-item ${a.status} kind-${a.kind}`}
            >
              <span className="glass-process-ico" aria-hidden>
                {a.status === "running" ? (
                  <Loader2 size={14} className="spin" />
                ) : isError ? (
                  <CircleAlert size={14} />
                ) : (
                  <Icon size={14} />
                )}
              </span>
              <div className="glass-process-body">
                <div className="glass-process-row">
                  <span className="t" title={a.title}>{a.title}</span>
                  {a.meta ? <span className="m">{a.meta}</span> : null}
                  {time ? <span className="time">{time}</span> : null}
                  {a.status === "done" && !isError ? (
                    <Check size={13} className="ok" />
                  ) : null}
                </div>
                {a.path ? <div className="glass-process-path">{a.path}</div> : null}

                {/* Spec 5: DecisionCard 渲染 — 目标 + 已知概念 + 风险 */}
                {isDecisionCard && decisionData ? (
                  <div className="glass-decision-card">
                    {decisionData.goal ? (
                      <div className="gdc-row">
                        <span className="gdc-icon">🎯</span>
                        <span className="gdc-label">目标</span>
                        <span className="gdc-value">{decisionData.goal}</span>
                      </div>
                    ) : null}
                    {decisionData.concepts && decisionData.concepts.length > 0 ? (
                      <div className="gdc-row">
                        <span className="gdc-icon">📚</span>
                        <span className="gdc-label">已知概念</span>
                        <span className="gdc-value gdc-concepts">
                          {decisionData.concepts.map((c) => (
                            <span key={c.id} className="gdc-chip">{c.label}</span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                    {decisionData.concept_edges && decisionData.concept_edges.length > 0 ? (
                      <div className="gdc-row">
                        <span className="gdc-icon">🔗</span>
                        <span className="gdc-label">因果链</span>
                        <span className="gdc-value gdc-edges">
                          {decisionData.concept_edges.slice(0, 3).map((e, i) => (
                            <span key={i} className="gdc-edge">
                              {e.from.split(":").pop()} <em>{e.type}</em> {e.to.split(":").pop()}
                            </span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                    {decisionData.memory_short_count !== undefined || decisionData.memory_long_count !== undefined ? (
                      <div className="gdc-row">
                        <span className="gdc-icon">🧠</span>
                        <span className="gdc-label">记忆</span>
                        <span className="gdc-value">
                          短期 {decisionData.memory_short_count || 0} · 长期 {decisionData.memory_long_count || 0}
                        </span>
                      </div>
                    ) : null}
                    {decisionData.risks && decisionData.risks.length > 0 ? (
                      <div className="gdc-row gdc-risk">
                        <span className="gdc-icon">⚠️</span>
                        <span className="gdc-label">风险</span>
                        <span className="gdc-value">
                          {decisionData.risks.map((r, i) => (
                            <span key={i} className="gdc-risk-chip">
                              {r.type}: {r.between.map((b) => b.split(":").pop()).join(" ⚡ ")}
                            </span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                  </div>
                ) : isRouteCard && routeData ? (
                  /* Spec 7+ DAAO RouteCard — 路由决策可视化 + 四维闭环反馈信号 */
                  <div className="glass-route-card">
                    <div className="grc-row">
                      <span className="grc-icon">🧭</span>
                      <span className="grc-label">路由</span>
                      <span className="grc-value">
                        <span className="grc-route">{routeData.route || "react"}</span>
                        <span className="grc-mode">{(routeData.work_mode || "craft").toUpperCase()}</span>
                        <span className="grc-steps">{routeData.max_steps || "?"} 步</span>
                        {typeof routeData.max_reflect_rounds === "number" ? (
                          <span className="grc-reflect">· {routeData.max_reflect_rounds} 轮反思</span>
                        ) : null}
                        {routeData.fallback ? <span className="grc-fallback">降级</span> : null}
                      </span>
                    </div>
                    {routeData.reason ? (
                      <div className="grc-row">
                        <span className="grc-icon">💡</span>
                        <span className="grc-label">理由</span>
                        <span className="grc-value grc-reason">{routeData.reason}</span>
                      </div>
                    ) : null}
                    {/* Spec 7+ 四维闭环反馈信号可视化 */}
                    {typeof routeData.difficulty_score === "number"
                      || typeof routeData.hera_hit_rate === "number"
                      || typeof routeData.recent_failure_rate === "number"
                      || typeof routeData.confidence === "number" ? (
                      <div className="grc-row grc-signals">
                        <span className="grc-icon">📊</span>
                        <span className="grc-label">信号</span>
                        <span className="grc-value grc-signal-bars">
                          {typeof routeData.difficulty_score === "number" ? (
                            <span className="grc-signal" title={`难度 ${(routeData.difficulty_score * 100).toFixed(0)}%`}>
                              <span className="grc-signal-label">难度</span>
                              <span className="grc-signal-bar">
                                <span
                                  className="grc-signal-fill grc-signal-difficulty"
                                  style={{ width: `${routeData.difficulty_score * 100}%` }}
                                />
                              </span>
                              <span className="grc-signal-val">{(routeData.difficulty_score * 100).toFixed(0)}%</span>
                            </span>
                          ) : null}
                          {typeof routeData.hera_hit_rate === "number" ? (
                            <span className="grc-signal" title={`HERA 命中率 ${(routeData.hera_hit_rate * 100).toFixed(0)}%`}>
                              <span className="grc-signal-label">HERA</span>
                              <span className="grc-signal-bar">
                                <span
                                  className="grc-signal-fill grc-signal-hera"
                                  style={{ width: `${routeData.hera_hit_rate * 100}%` }}
                                />
                              </span>
                              <span className="grc-signal-val">{(routeData.hera_hit_rate * 100).toFixed(0)}%</span>
                            </span>
                          ) : null}
                          {typeof routeData.recent_failure_rate === "number" && routeData.recent_failure_rate > 0 ? (
                            <span className="grc-signal" title={`最近失败率 ${(routeData.recent_failure_rate * 100).toFixed(0)}%`}>
                              <span className="grc-signal-label">失败率</span>
                              <span className="grc-signal-bar">
                                <span
                                  className="grc-signal-fill grc-signal-fail"
                                  style={{ width: `${routeData.recent_failure_rate * 100}%` }}
                                />
                              </span>
                              <span className="grc-signal-val">{(routeData.recent_failure_rate * 100).toFixed(0)}%</span>
                            </span>
                          ) : null}
                          {typeof routeData.confidence === "number" ? (
                            <span className="grc-signal" title={`置信度 ${(routeData.confidence * 100).toFixed(0)}%`}>
                              <span className="grc-signal-label">置信</span>
                              <span className="grc-signal-bar">
                                <span
                                  className="grc-signal-fill grc-signal-conf"
                                  style={{ width: `${routeData.confidence * 100}%` }}
                                />
                              </span>
                              <span className="grc-signal-val">{(routeData.confidence * 100).toFixed(0)}%</span>
                            </span>
                          ) : null}
                        </span>
                      </div>
                    ) : null}
                    {routeData.workspace_kind ? (
                      <div className="grc-row">
                        <span className="grc-icon">📦</span>
                        <span className="grc-label">类型</span>
                        <span className="grc-value">{routeData.workspace_kind}</span>
                      </div>
                    ) : null}
                    {routeData.tool_subset && routeData.tool_subset.length > 0 ? (
                      <div className="grc-row">
                        <span className="grc-icon">🔧</span>
                        <span className="grc-label">工具集</span>
                        <span className="grc-value grc-tools">
                          {routeData.tool_subset.map((t) => (
                            <span key={t} className="grc-tool-chip">{t}</span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                  </div>
                ) : isCriticVerdictCard && criticVerdictData ? (
                  /* Spec 5: CriticVerdictCard — 独立第三方 Critic 审查结论 */
                  <div className={`glass-critic-card ${criticVerdictData.passed === false ? "critic-failed" : "critic-passed"}`}>
                    <div className="gcc-row gcc-header">
                      <span className="gcc-icon">{criticVerdictData.passed === false ? "⚠️" : "✅"}</span>
                      <span className="gcc-label">Critic 审查</span>
                      <span className="gcc-verdict">{criticVerdictData.passed === false ? "未通过" : "通过"}</span>
                      {typeof criticVerdictData.score === "number" ? (
                        <span className="gcc-score">
                          <span className="gcc-score-bar">
                            <span
                              className="gcc-score-fill"
                              style={{ width: `${criticVerdictData.score * 100}%` }}
                            />
                          </span>
                          <span className="gcc-score-val">{(criticVerdictData.score * 100).toFixed(0)}%</span>
                        </span>
                      ) : null}
                    </div>
                    {criticVerdictData.issues && criticVerdictData.issues.length > 0 ? (
                      <div className="gcc-row">
                        <span className="gcc-icon">🐛</span>
                        <span className="gcc-label">问题</span>
                        <span className="gcc-value gcc-issues">
                          {criticVerdictData.issues.slice(0, 4).map((issue, i) => (
                            <span key={i} className="gcc-issue-chip">{issue}</span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                    {criticVerdictData.suggestions && criticVerdictData.suggestions.length > 0 ? (
                      <div className="gcc-row">
                        <span className="gcc-icon">💡</span>
                        <span className="gcc-label">建议</span>
                        <span className="gcc-value gcc-suggestions">
                          {criticVerdictData.suggestions.slice(0, 3).map((sug, i) => (
                            <span key={i} className="gcc-suggestion-chip">{sug}</span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                  </div>
                ) : isReflectionToSkillCard && reflectionToSkillData ? (
                  /* Spec 7+: ReflectionToSkillCard — VMAO 反思已写入 HERA 失败技能库 */
                  <div className="glass-reflection-to-skill-card">
                    <div className="grts-row grts-header">
                      <span className="grts-icon">🔄</span>
                      <span className="grts-label">四维闭环</span>
                      <span className="grts-action">VMAO 反思 → HERA 失败技能库</span>
                      {typeof reflectionToSkillData.round === "number" ? (
                        <span className="grts-round">第 {reflectionToSkillData.round} 轮</span>
                      ) : null}
                    </div>
                    <div className="grts-row">
                      <span className="grts-icon">💾</span>
                      <span className="grts-label">状态</span>
                      <span className="grts-value">
                        {reflectionToSkillData.saved ? "已入库" : "未入库"} · 库存 {reflectionToSkillData.library_total || 0}
                      </span>
                    </div>
                    <div className="grts-note">
                      反思经验已沉淀，下次类似任务将作为"失败技能"召回，避免重复试错
                    </div>
                  </div>
                ) : isGuardrailCard && guardrailData ? (
                  /* 史诗级优化: GuardrailCard — 产物校验 + Reflexion 修复循环 */
                  <div className="glass-guardrail-card">
                    <div className="grc-row grc-header">
                      <span className="grc-icon">{guardrailData.repair_attempt ? "🔧" : "🛡️"}</span>
                      <span className="grc-label">{guardrailData.repair_attempt ? "Reflexion 修复" : "Guardrail 校验"}</span>
                      <span className={`grc-status ${guardrailData.passed ? "grc-pass" : "grc-fail"}`}>
                        {guardrailData.passed ? "通过" : "未通过"}
                      </span>
                    </div>
                    {guardrailData.summary ? (
                      <div className="grc-row">
                        <span className="grc-icon">📋</span>
                        <span className="grc-label">摘要</span>
                        <span className="grc-value">{guardrailData.summary}</span>
                      </div>
                    ) : null}
                    {guardrailData.missing && guardrailData.missing.length > 0 ? (
                      <div className="grc-row">
                        <span className="grc-icon">⚠️</span>
                        <span className="grc-label">缺失</span>
                        <span className="grc-value grc-missing">
                          {guardrailData.missing.map((m, i) => (
                            <span key={i} className="grc-missing-chip">{m}</span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                    {guardrailData.issues && guardrailData.issues.length > 0 ? (
                      <div className="grc-row">
                        <span className="grc-icon">🔍</span>
                        <span className="grc-label">问题</span>
                        <span className="grc-value grc-issues">
                          {guardrailData.issues.flat().slice(0, 4).map((iss, i) => (
                            <span key={i} className="grc-issue-chip">{iss}</span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                    {guardrailData.repair_attempt && typeof guardrailData.artifacts_after === "number" ? (
                      <div className="grc-note">
                        修复后产物数: {guardrailData.artifacts_after}
                      </div>
                    ) : null}
                  </div>
                ) : isReflectionCard && reflectionData ? (
                  /* Spec 6 VMAO: ReflectionCard — Reflexion 自反思 */
                  <div className="glass-reflection-card">
                    <div className="grfc-row grfc-header">
                      <span className="grfc-icon">🔍</span>
                      <span className="grfc-label">VMAO 反思</span>
                      <span className="grfc-round">第 {reflectionData.round || 1} 轮</span>
                    </div>
                    {reflectionData.reason ? (
                      <div className="grfc-row">
                        <span className="grfc-icon">⚠️</span>
                        <span className="grfc-label">触发</span>
                        <span className="grfc-value">{reflectionData.reason}</span>
                      </div>
                    ) : null}
                    {reflectionData.reflection ? (
                      <div className="grfc-row">
                        <span className="grfc-icon">💭</span>
                        <span className="grfc-label">反思</span>
                        <span className="grfc-value grfc-reflection-text">{reflectionData.reflection}</span>
                      </div>
                    ) : null}
                    {reflectionData.previous_failures && reflectionData.previous_failures.length > 0 ? (
                      <div className="grfc-row">
                        <span className="grfc-icon">❌</span>
                        <span className="grfc-label">失败</span>
                        <span className="grfc-value grfc-failures">
                          {reflectionData.previous_failures.slice(0, 3).map((f, i) => (
                            <span key={i} className="grfc-failure-chip">
                              {f.name}: {f.error.slice(0, 80)}
                            </span>
                          ))}
                        </span>
                      </div>
                    ) : null}
                  </div>
                ) : isSkillRetrievedCard && skillRetrievedData ? (
                  /* Spec 6 HERA: SkillRetrievedCard — 召回历史技能 */
                  <div className="glass-skill-card glass-skill-retrieved">
                    <div className="gsc-row gsc-header">
                      <span className="gsc-icon">🗄️</span>
                      <span className="gsc-label">HERA 召回</span>
                      <span className="gsc-count">
                        {skillRetrievedData.skills?.length || 0} 个 · 库存 {skillRetrievedData.total_in_library || 0}
                      </span>
                    </div>
                    {skillRetrievedData.skills && skillRetrievedData.skills.length > 0 ? (
                      <div className="gsc-skills">
                        {skillRetrievedData.skills.slice(0, 3).map((s, i) => (
                          <div key={i} className="gsc-skill-item">
                            <span className="gsc-skill-sig">{s.task_signature}</span>
                            <span className="gsc-skill-meta">×{s.usage_count} · {s.workspace_kind}</span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="gsc-empty">技能库为空，本次为首跑</div>
                    )}
                  </div>
                ) : isSkillSavedCard && skillSavedData ? (
                  /* Spec 6 HERA: SkillSavedCard — 技能已固化 */
                  <div className="glass-skill-card glass-skill-saved">
                    <div className="gsc-row gsc-header">
                      <span className="gsc-icon">💾</span>
                      <span className="gsc-label">HERA 固化</span>
                      <span className="gsc-count">库存 {skillSavedData.library_total || 0}</span>
                    </div>
                    {skillSavedData.task_signature ? (
                      <div className="gsc-row">
                        <span className="gsc-icon">📝</span>
                        <span className="gsc-label">技能</span>
                        <span className="gsc-value">{skillSavedData.task_signature}</span>
                      </div>
                    ) : null}
                  </div>
                ) : isFewShotRetrievedCard && fewShotRetrievedData ? (
                  /* Spec 6 Self-Optimizing: FewShotRetrievedCard — 召回 few-shot 示例 */
                  <div className="glass-fewshot-card">
                    <div className="gfc-row gfc-header">
                      <span className="gfc-icon">🎯</span>
                      <span className="gfc-label">Self-Optimizing 召回</span>
                      <span className="gfc-count">
                        {fewShotRetrievedData.examples?.length || 0} 个 · 库存 {fewShotRetrievedData.total_in_library || 0}
                      </span>
                    </div>
                    {fewShotRetrievedData.examples && fewShotRetrievedData.examples.length > 0 ? (
                      <div className="gfc-examples">
                        {fewShotRetrievedData.examples.slice(0, 3).map((ex, i) => (
                          <div key={i} className="gfc-example-item">
                            <span className="gfc-example-sig">{ex.task_signature}</span>
                            <span className="gfc-example-meta">
                              score {ex.score.toFixed(2)} · ×{ex.usage_count} · {ex.workspace_kind}
                              {ex.tool_sequence && ex.tool_sequence.length > 0
                                ? ` · ${ex.tool_sequence.join(" -> ")}`
                                : ""}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="gsc-empty">示例库为空，本次为首跑</div>
                    )}
                  </div>
                ) : isFewShotSavedCard && fewShotSavedData ? (
                  /* Spec 6 Self-Optimizing: FewShotSavedCard — 离线轨迹沉淀 */
                  <div className="glass-fewshot-card">
                    <div className="gfc-row gfc-header">
                      <span className="gfc-icon">🔮</span>
                      <span className="gfc-label">Self-Optimizing 沉淀</span>
                      <span className="gfc-count">
                        库存 {fewShotSavedData.library_total || 0}
                        {typeof fewShotSavedData.score === "number"
                          ? ` · score ${fewShotSavedData.score.toFixed(2)}`
                          : ""}
                      </span>
                    </div>
                    {fewShotSavedData.task_signature ? (
                      <div className="gfc-row">
                        <span className="gfc-icon">📝</span>
                        <span className="gfc-label">示例</span>
                        <span className="gfc-value">{fewShotSavedData.task_signature}</span>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <>
                    {hasDetail ? (
                      <button
                        type="button"
                        className="glass-process-detail-toggle"
                        onClick={() => toggle(a.id)}
                        aria-expanded={isOpen}
                      >
                        {isThink
                          ? isOpen ? "收起思考" : "展开思考"
                          : isOpen ? "收起详情" : "展开详情"}
                      </button>
                    ) : null}
                    {hasDetail && isOpen ? (
                      <pre className="glass-process-detail">{a.detail}</pre>
                    ) : hasDetail && !isOpen && isThink ? (
                      <div className="glass-process-detail-preview">
                        {truncate(a.detail!, 120)}
                      </div>
                    ) : null}
                  </>
                )}

                {a.path && onOpenDiff && (a.kind === "edit" || a.kind === "write") ? (
                  <button
                    type="button"
                    className="glass-process-diff"
                    onClick={() => onOpenDiff(a.path!)}
                  >
                    查看变更
                  </button>
                ) : null}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
