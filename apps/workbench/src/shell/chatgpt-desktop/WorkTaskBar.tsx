/**
 * WorkBuddy 任务条：模式 · 标题 · 流水线步骤 · 进化内核 · 实时状态
 */

import type { EvolutionInfo, WorkExecMode, WorkMission, WorkPipelineInfo } from "./fnixRuntime";

const STEPS = [
  { id: "mission", label: "拆解" },
  { id: "plan", label: "规划" },
  { id: "run", label: "执行" },
  { id: "done", label: "验收" },
] as const;

function activeStepIndex(
  streaming: boolean,
  mission: WorkMission | null,
  pipeline: WorkPipelineInfo | null,
  healRound: { current: number; max: number } | null,
): number {
  if (!streaming && (mission || pipeline)) return healRound ? 4 : 3;
  if (streaming && healRound) return 3;
  if (pipeline) return 2;
  if (mission) return 1;
  if (streaming) return 0;
  return -1;
}

function evolutionLabel(evo: EvolutionInfo | null): string | null {
  if (!evo) return null;
  const parts: string[] = [];
  if (typeof evo.ktg_paths === "number") parts.push(`KTG ${evo.ktg_paths}`);
  else if (evo.ktg) parts.push("KTG");
  if (evo.stp) parts.push("STP");
  else if (typeof evo.ktg_paths === "number") parts.push("STP");
  if (evo.mfp || evo.mfp_result) parts.push("MFP");
  const mem = evo.memory;
  if (mem && typeof mem === "object") {
    const n = (mem.short || 0) + (mem.long || 0);
    if (n > 0) parts.push(`Mem ${n}`);
  } else if (mem === true) {
    parts.push("Mem");
  }
  if (evo.reasoning_mode) parts.push(String(evo.reasoning_mode));
  if (!parts.length && evo.step) parts.push(String(evo.step));
  return parts.length ? parts.join(" · ") : "Evolution";
}

interface Props {
  workMode: WorkExecMode;
  mission: WorkMission | null;
  pipeline: WorkPipelineInfo | null;
  evolution?: EvolutionInfo | null;
  status: string | null;
  streaming: boolean;
  fallbackTitle?: string;
  /** Heal 轮次进度；非 null 时在 run 与 done 之间显示"修复 N/M"步骤 */
  healRound?: { current: number; max: number } | null;
}

export function WorkTaskBar({
  workMode,
  mission,
  pipeline,
  evolution = null,
  status,
  streaming,
  fallbackTitle,
  healRound = null,
}: Props) {
  const title = String(mission?.title || fallbackTitle || "新任务");
  const kind = String(mission?.workspace_kind || "");
  const reason = String(pipeline?.reasoning_mode || "");
  const stepIdx = activeStepIndex(streaming, mission, pipeline, healRound);
  const evoLabel = evolutionLabel(evolution);
  // 有 healRound 时，在 run 与 done 之间插入"修复 N/M"步
  const healStep = healRound
    ? [{ id: "heal", label: `修复 ${healRound.current}/${healRound.max}` }]
    : [];
  const steps = [...STEPS.slice(0, 3), ...healStep, ...STEPS.slice(3)];

  if (!mission && !status && !pipeline && !streaming && !evolution) return null;

  return (
    <div className="wb-task-bar" aria-live="polite">
      <div className="wb-task-top">
        <span className={`wb-task-badge ${workMode}`}>{workMode}</span>
        <span className="wb-task-title" title={title}>
          {title}
        </span>
        {kind ? <span className="wb-task-chip">{kind}</span> : null}
        {reason ? <span className="wb-task-chip dim">{reason}</span> : null}
        {evoLabel ? (
          <span className="wb-task-chip evo" title="自进化内核（KTG / STP / MFP）">
            {evoLabel}
          </span>
        ) : null}
        {streaming ? <span className="wb-task-live">进行中</span> : null}
      </div>
      {stepIdx >= 0 ? (
        <div className="wb-task-steps">
          {steps.map((s, i) => {
            const state = i < stepIdx ? "done" : i === stepIdx ? "on" : "";
            const isHeal = s.id === "heal";
            return (
              <div key={s.id} className={`wb-step ${state}${isHeal ? " heal" : ""}`}>
                <i />
                <span>{s.label}</span>
              </div>
            );
          })}
        </div>
      ) : null}
      {status ? <div className="wb-task-status">{status}</div> : null}
    </div>
  );
}
