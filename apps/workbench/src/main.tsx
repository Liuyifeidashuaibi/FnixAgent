/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import ErrorBoundary from "./components/ErrorBoundary";
import "./monacoSetup";
import { initObservability } from "./observability";
import { initializeFnixRuntime } from "./lib/fnixBridge";

initObservability();

async function boot() {
  const root = document.getElementById("root")!;

  // Tauri selects free local ports and starts agentd/fnix-local. Browser dev
  // falls back to VITE_API_BASE/the Vite proxy when this command is unavailable.
  await initializeFnixRuntime();

  const { default: DesktopApp } = await import("./shell/desktop/DesktopApp");
  createRoot(root).render(
    <StrictMode>
      <ErrorBoundary>
        <DesktopApp />
      </ErrorBoundary>
    </StrictMode>,
  );
}

boot().catch((err) => {
  console.error("[boot] failed to start:", err);
  const root = document.getElementById("root");
  if (root) {
    root.innerHTML = "";
    const box = document.createElement("div");
    box.style.cssText =
      "font:14px/1.6 system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 20px;color:#b91c1c;";
    box.textContent = `应用启动失败：${err instanceof Error ? err.message : String(err)}`;
    root.appendChild(box);
  }
});
