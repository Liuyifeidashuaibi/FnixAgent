/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Shell domain transition guards — illegal-state elimination without XState.
 * workspace / session / run / review must agree before side effects.
 */

import type { ShellMode } from "./shellTypes";
import type { RunPhase } from "./runStore";
import type { ReviewApplyStatus } from "./reviewStore";

export type ApplyGuardInput = {
  runPhase: RunPhase;
  applyStatus: ReviewApplyStatus;
  streaming?: boolean;
};

export type UndoGuardInput = ApplyGuardInput & {
  lastChangesetId: string | null | undefined;
};

export type ReviewOpenGuardInput = {
  mode: ShellMode;
  hasPending: boolean;
};

/** Accept / partial Accept — never while streaming or mid-apply/undo. */
export function canApplyReview(g: ApplyGuardInput): boolean {
  if (g.streaming || g.runPhase === "streaming" || g.runPhase === "stopping") return false;
  if (g.applyStatus === "applying" || g.applyStatus === "undoing") return false;
  return true;
}

/** Undo last changeset — blocked while streaming or another apply in flight. */
export function canUndoReview(g: UndoGuardInput): boolean {
  if (!g.lastChangesetId) return false;
  return canApplyReview(g);
}

/** Review pane only meaningful in Code product mode. */
export function canOpenReview(g: ReviewOpenGuardInput): boolean {
  return g.mode === "code" && g.hasPending;
}

/** Start a new Work/Code stream. */
export function canStartRun(phase: RunPhase): boolean {
  return phase === "idle" || phase === "error" || phase === "done";
}
