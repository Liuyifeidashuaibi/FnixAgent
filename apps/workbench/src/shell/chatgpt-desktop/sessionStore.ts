/**
 * Thin shell session store — mode / pane / Studio Panel (unified right inspector).
 * Persists mode + pane + panel state to localStorage so a reload restores the shell.
 *
 * v2: 右侧三面板（CanvasDock / WorkResults / ReviewPane）合并为单一 Studio Panel，
 *     双布尔 canvasDockOpen / reviewOpen 收敛为 inspectorOpen + inspectorTab。
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { ShellMode, ShellPane } from "./shellTypes";

/** Studio Panel 视图 — 画布 / 结果(Work) / 评审(Codex) / 终端 / 浏览器 */
export type StudioTab = "canvas" | "results" | "review" | "terminal" | "browser";

interface SessionState {
  mode: ShellMode;
  pane: ShellPane;
  /** Studio Panel 开关（替代 canvasDockOpen + reviewOpen）*/
  inspectorOpen: boolean;
  /** Studio Panel 当前视图 */
  inspectorTab: StudioTab;
  /** 已钉选到画布的文件路径列表（最多 8 个，FIFO 淘汰）*/
  pinnedArtifacts: string[];
  /** 已置顶的会话 ID 列表（置顶区常驻列表顶部，不参与时间分组）*/
  pinnedThreadIds: string[];
  setMode: (mode: ShellMode) => void;
  setPane: (pane: ShellPane) => void;
  setInspectorOpen: (open: boolean) => void;
  setInspectorTab: (tab: StudioTab) => void;
  toggleInspector: () => void;
  /** 钉选文件到画布；已存在则提前到首位；超过 8 个淘汰最旧的；自动展开面板并切到画布 */
  pinArtifact: (path: string) => void;
  /** 取消钉选（不强制关闭面板 — 用户可能正在看别的视图）*/
  unpinArtifact: (path: string) => void;
  /** 清空所有钉选（不强制关闭面板）*/
  clearPinnedArtifacts: () => void;
  /** 置顶/取消置顶会话；已存在则移除，不存在则插入首位 */
  toggleThreadPin: (id: string) => void;
}

export type { ShellMode, ShellPane };

// Guard against environments without localStorage (e.g. non-browser import).
const safeStorage = {
  getItem: (name: string): string | null =>
    typeof localStorage !== "undefined" ? localStorage.getItem(name) : null,
  setItem: (name: string, value: string): void => {
    if (typeof localStorage !== "undefined") localStorage.setItem(name, value);
  },
  removeItem: (name: string): void => {
    if (typeof localStorage !== "undefined") localStorage.removeItem(name);
  },
};

const isStudioTab = (t: unknown): t is StudioTab =>
  t === "canvas" || t === "results" || t === "review" || t === "terminal" || t === "browser";

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      mode: "work",
      pane: "home",
      inspectorOpen: false,
      inspectorTab: "canvas",
      pinnedArtifacts: [],
      pinnedThreadIds: [],
      setMode: (mode) =>
        set({
          mode,
          // review 仅 Codex 合法 — 切回 Work 时回落到画布
          inspectorTab: mode === "work" && get().inspectorTab === "review" ? "canvas" : get().inspectorTab,
        }),
      setPane: (pane) => set({ pane }),
      setInspectorOpen: (open) => set({ inspectorOpen: open }),
      setInspectorTab: (tab) => set({ inspectorTab: tab, inspectorOpen: true }),
      toggleInspector: () => set({ inspectorOpen: !get().inspectorOpen }),
      pinArtifact: (path) => {
        const prev = get().pinnedArtifacts;
        // 已存在则提前到首位；不存在则插入首位；超过 8 个淘汰最旧的
        const next = [path, ...prev.filter((p) => p !== path)].slice(0, 8);
        set({ pinnedArtifacts: next, inspectorOpen: true, inspectorTab: "canvas" });
      },
      unpinArtifact: (path) => {
        const next = get().pinnedArtifacts.filter((p) => p !== path);
        set({ pinnedArtifacts: next });
      },
      clearPinnedArtifacts: () => set({ pinnedArtifacts: [] }),
      toggleThreadPin: (id) => {
        const prev = get().pinnedThreadIds;
        const next = prev.includes(id)
          ? prev.filter((t) => t !== id)
          : [id, ...prev].slice(0, 20);
        set({ pinnedThreadIds: next });
      },
    }),
    {
      name: "fnix-shell-session",
      storage: createJSONStorage(() => safeStorage),
      // Only persist data, never the action functions.
      partialize: (s) => ({
        mode: s.mode,
        pane: s.pane,
        inspectorOpen: s.inspectorOpen,
        inspectorTab: s.inspectorTab,
        pinnedArtifacts: s.pinnedArtifacts,
        pinnedThreadIds: s.pinnedThreadIds,
      }),
      // 旧版本持久化的是 canvasDockOpen/reviewOpen — 迁移时只认新字段，
      // 非法 inspectorTab（如旧数据缺失）回落到 canvas。
      merge: (persisted, current) => {
        const raw = (persisted ?? {}) as Partial<SessionState>;
        return {
          ...current,
          ...raw,
          inspectorTab: isStudioTab(raw.inspectorTab) ? raw.inspectorTab : "canvas",
          pinnedArtifacts: Array.isArray(raw.pinnedArtifacts) ? raw.pinnedArtifacts : [],
          pinnedThreadIds: Array.isArray(raw.pinnedThreadIds) ? raw.pinnedThreadIds : [],
        };
      },
    },
  ),
);
