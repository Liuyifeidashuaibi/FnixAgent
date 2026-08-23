/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code is proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * useStreamStatus — 流式状态管理 hook
 * 借鉴 Cline（计时器）+ Cursor（分阶段标签）+ OpenHands（事件驱动）的设计
 *
 * 功能：
 *   1. 从后端 status 字符串推断当前阶段（connecting/thinking/planning/executing/reviewing/healing/done）
 *   2. 显示已耗时秒数，让用户知道系统在工作
 *   3. 超过 10s 显示柔和提示"可能需要一些时间"
 */

import { useEffect, useRef, useState } from "react";

export type StreamPhase =
  | "connecting"
  | "thinking"
  | "planning"
  | "executing"
  | "reviewing"
  | "healing"
  | "done"
  | "error";

const PHASE_LABELS: Record<StreamPhase, string> = {
  connecting: "正在连接…",
  thinking: "正在思考…",
  planning: "正在规划…",
  executing: "正在执行…",
  reviewing: "正在审查…",
  healing: "正在修复…",
  done: "完成",
  error: "出错",
};

export function useStreamStatus(status: string | null, streaming: boolean) {
  const [phase, setPhase] = useState<StreamPhase>("connecting");
  const [elapsed, setElapsed] = useState(0);
  const startTime = useRef<number | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!streaming) {
      setElapsed(0);
      startTime.current = null;
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    if (startTime.current === null) {
      startTime.current = Date.now();
      timerRef.current = window.setInterval(() => {
        setElapsed(Math.floor((Date.now() - (startTime.current || Date.now())) / 1000));
      }, 1000);
    }

    // 从 status 推断 phase
    const s = (status || "").toLowerCase();
    if (!s || s.includes("connect") || s.includes("连接")) setPhase("connecting");
    else if (s.includes("think") || s.includes("思考") || s.includes("分析")) setPhase("thinking");
    else if (s.includes("plan") || s.includes("规划")) setPhase("planning");
    else if (s.includes("execut") || s.includes("run") || s.includes("执行") || s.includes("preview")) setPhase("executing");
    else if (s.includes("review") || s.includes("审查")) setPhase("reviewing");
    else if (s.includes("heal") || s.includes("修复")) setPhase("healing");
    else if (s.includes("compac")) setPhase("thinking"); // compaction 归类为思考
    else if (s.includes("critic")) setPhase("reviewing"); // critic 归类为审查
    else if (s.includes("done") || s.includes("完成")) setPhase("done");
    else if (s.includes("error") || s.includes("出错")) setPhase("error");
    else setPhase("thinking"); // 有状态但未匹配时默认思考中

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [status, streaming]);

  // 超过 10s 显示柔和提示
  const longWait = elapsed >= 10;
  const label = PHASE_LABELS[phase];

  return { phase, label, elapsed, longWait };
}
