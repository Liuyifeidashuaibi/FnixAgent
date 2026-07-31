/**
 * Run domain store — streaming phase for Work/Code agent turns.
 */

import { create } from "zustand";

export type RunPhase = "idle" | "streaming" | "stopping" | "done" | "error";

interface RunState {
  phase: RunPhase;
  status: string | null;
  error: string | null;
  start: (status?: string | null) => void;
  setStatus: (status: string | null) => void;
  setError: (error: string | null) => void;
  requestStop: () => void;
  finish: (ok: boolean) => void;
  reset: () => void;
}

export const useRunStore = create<RunState>((set) => ({
  phase: "idle",
  status: null,
  error: null,
  start: (status = null) => set({ phase: "streaming", status, error: null }),
  setStatus: (status) => set({ status }),
  setError: (error) =>
    set((s) => ({
      error,
      phase: error ? "error" : s.phase,
    })),
  requestStop: () =>
    set((s) => (s.phase === "streaming" ? { phase: "stopping" } : s)),
  finish: (ok) =>
    set({
      phase: ok ? "done" : "error",
      status: null,
    }),
  reset: () => set({ phase: "idle", status: null, error: null }),
}));
