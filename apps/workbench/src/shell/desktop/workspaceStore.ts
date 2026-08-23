/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/**
 * Workspace domain store — open project + recent list (SSOT).
 */

import { create } from "zustand";
import type { RecentProject } from "../../utils/tauri";

interface WorkspaceState {
  projectPath: string;
  recentProjects: RecentProject[];
  agentdOk: boolean | null;
  setProjectPath: (path: string) => void;
  setRecentProjects: (projects: RecentProject[]) => void;
  upsertRecent: (path: string) => void;
  setAgentdOk: (ok: boolean | null) => void;
  clearProject: () => void;
}

export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  projectPath: "",
  recentProjects: [],
  agentdOk: null,
  setProjectPath: (path) => set({ projectPath: path }),
  setRecentProjects: (projects) => set({ recentProjects: projects }),
  upsertRecent: (path) =>
    set((s) => ({
      projectPath: path,
      recentProjects: [
        { path, openedAt: Date.now() },
        ...s.recentProjects.filter((p) => p.path !== path),
      ].slice(0, 12),
    })),
  setAgentdOk: (ok) => set({ agentdOk: ok }),
  clearProject: () => set({ projectPath: "" }),
}));
