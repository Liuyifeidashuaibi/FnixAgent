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
} from "../shell/desktop/shellFsm";

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

  it("review opens whenever pending changes exist (any mode)", () => {
    // BUG-6 fix 后的契约：pickChatBackend 可能将 Work 模式路由到 Code 管线
    // （如 Work 模式下输入仓库级改码任务），此时 fileChanges 会填充，
    // 评审面板必须能打开，否则 Accept 按钮永不出现、preview 写盘无法落盘。
    expect(canOpenReview({ mode: "work", hasPending: true })).toBe(true);
    expect(canOpenReview({ mode: "code", hasPending: true })).toBe(true);
    // 无待审变更时任何模式都不打开
    expect(canOpenReview({ mode: "work", hasPending: false })).toBe(false);
    expect(canOpenReview({ mode: "code", hasPending: false })).toBe(false);
  });

  it("canStartRun allows idle/error/done", () => {
    expect(canStartRun("idle")).toBe(true);
    expect(canStartRun("error")).toBe(true);
    expect(canStartRun("done")).toBe(true);
    expect(canStartRun("streaming")).toBe(false);
    expect(canStartRun("stopping")).toBe(false);
  });
});
