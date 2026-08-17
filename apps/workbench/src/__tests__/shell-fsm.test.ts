/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { describe, expect, it } from "vitest";
import {
  canApplyReview,
  canOpenReview,
  canStartRun,
  canUndoReview,
} from "../shell/chatgpt-desktop/shellFsm";

describe("shellFsm", () => {
  it("blocks apply while streaming", () => {
    expect(
      canApplyReview({ runPhase: "streaming", applyStatus: "idle", streaming: true }),
    ).toBe(false);
  });

  it("blocks apply while applying/undoing", () => {
    expect(canApplyReview({ runPhase: "idle", applyStatus: "applying" })).toBe(false);
    expect(canApplyReview({ runPhase: "idle", applyStatus: "undoing" })).toBe(false);
  });

  it("allows apply when idle", () => {
    expect(canApplyReview({ runPhase: "idle", applyStatus: "idle" })).toBe(true);
    expect(canApplyReview({ runPhase: "done", applyStatus: "applied" })).toBe(true);
  });

  it("undo requires changeset and idle apply", () => {
    expect(
      canUndoReview({
        runPhase: "idle",
        applyStatus: "idle",
        lastChangesetId: null,
      }),
    ).toBe(false);
    expect(
      canUndoReview({
        runPhase: "idle",
        applyStatus: "idle",
        lastChangesetId: "cs-1",
      }),
    ).toBe(true);
  });

  it("review open only in codex with pending", () => {
    expect(canOpenReview({ mode: "work", hasPending: true })).toBe(false);
    expect(canOpenReview({ mode: "codex", hasPending: false })).toBe(false);
    expect(canOpenReview({ mode: "codex", hasPending: true })).toBe(true);
  });

  it("canStartRun allows idle/error/done", () => {
    expect(canStartRun("idle")).toBe(true);
    expect(canStartRun("error")).toBe(true);
    expect(canStartRun("done")).toBe(true);
    expect(canStartRun("streaming")).toBe(false);
    expect(canStartRun("stopping")).toBe(false);
  });
});
