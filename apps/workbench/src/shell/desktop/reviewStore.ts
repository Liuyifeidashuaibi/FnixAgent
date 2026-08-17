/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Thin Code Review domain store — pending diffs, apply status, undo changeset.
 */

import { create } from "zustand";
import type { CodeFileChange } from "./fnixRuntime";

export type ReviewApplyStatus = "idle" | "applying" | "applied" | "failed" | "undoing";

interface ReviewState {
  pending: CodeFileChange[];
  selectedPath: string | null;
  applyStatus: ReviewApplyStatus;
  applyMessage: string | null;
  lastChangesetId: string | null;
  setPending: (changes: CodeFileChange[]) => void;
  selectPath: (path: string | null) => void;
  setApplyStatus: (status: ReviewApplyStatus, message?: string | null) => void;
  setChangesetId: (id: string | null) => void;
  /** Reject pending diffs; keep lastChangesetId so Undo still works. */
  clearPending: () => void;
}

export const useReviewStore = create<ReviewState>((set) => ({
  pending: [],
  selectedPath: null,
  applyStatus: "idle",
  applyMessage: null,
  lastChangesetId: null,
  setPending: (changes) =>
    set((s) => ({
      pending: changes,
      selectedPath:
        changes.find((c) => c.path === s.selectedPath)?.path ?? changes[0]?.path ?? null,
      applyStatus: changes.length ? s.applyStatus : "idle",
      applyMessage: changes.length ? s.applyMessage : null,
    })),
  selectPath: (path) => set({ selectedPath: path }),
  setApplyStatus: (status, message = null) =>
    set({ applyStatus: status, applyMessage: message }),
  setChangesetId: (id) => set({ lastChangesetId: id }),
  clearPending: () =>
    set({
      pending: [],
      selectedPath: null,
      applyStatus: "idle",
      applyMessage: null,
    }),
}));
