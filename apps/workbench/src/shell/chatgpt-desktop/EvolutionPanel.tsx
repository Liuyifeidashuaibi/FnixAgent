/** 将进化数据翻译成用户能理解、能判断是否有帮助的一行摘要。 */

import type { EvolutionInfo } from "./fnixRuntime";
import type { EvolutionRecord } from "./useChatFlow";
import "./EvolutionPanel.css";

interface Props {
  history: EvolutionRecord[];
  current: EvolutionInfo | null;
  streaming: boolean;
}

function memoryCount(evo: EvolutionInfo): number {
  const mem = evo.memory;
  if (!mem || typeof mem === "boolean") return 0;
  return (mem.short || 0) + (mem.long || 0);
}

export function EvolutionPanel({ history, current, streaming: _streaming }: Props) {
  const latest = history.length > 0 ? history[history.length - 1]?.evolution : null;
  const evo = current || latest;
  if (!evo) return null;

  const insights: { key: string; text: string; title: string }[] = [];
  if (typeof evo.ktg_paths === "number" && evo.ktg_paths > 0) {
    insights.push({
      key: "ktg",
      text: `KTG · 参考 ${evo.ktg_paths} 条知识路径`,
      title: "知识图谱为本轮任务找到的相关推理路径",
    });
  }

  const concepts = Array.isArray(evo.concepts)
    ? evo.concepts.map(String).filter(Boolean)
    : [];
  if (concepts.length > 0) {
    const visible = concepts.slice(0, 3).join("、");
    insights.push({
      key: "stp",
      text: `STP · 识别 ${visible}${concepts.length > 3 ? ` 等 ${concepts.length} 个概念` : ""}`,
      title: "本轮任务识别并采用的相关概念",
    });
  }

  const memories = memoryCount(evo);
  if (memories > 0) {
    insights.push({
      key: "mfp",
      text: `MFP · 参考 ${memories} 条历史经验`,
      title: "本轮回答实际参考的短期与长期记忆",
    });
  }

  if (insights.length === 0) return null;

  return (
    <div className="evo-summary" role="status" aria-live="polite" aria-label="本轮辅助信息">
      {insights.map((item) => (
        <span key={item.key} className="evo-summary-item" title={item.title}>
          {item.text}
        </span>
      ))}
    </div>
  );
}
