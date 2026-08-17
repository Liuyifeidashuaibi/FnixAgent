/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

/** Fnix product metadata (About / diagnostics). */

export const FNIX_WEBSITE_URL = "https://github.com/fnixagent/fnixagent";
export const FNIX_GITHUB_URL = "https://github.com/fnixagent/fnixagent";
export const FNIX_DISCORD_URL = "";
export const FNIX_LICENSE = "Apache-2.0";
export const FNIX_VERSION = "1.0.0";
export const FNIX_BUILD_NUMBER = "workbench.1";
export const FNIX_RELEASE_DATE = "2026-07-18";
export const FNIX_RELEASE_CHANNEL = "internal";

/** Optional; empty by default — no third-party crash phone-home. */
export const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN || "";

export const ALPHA_RELEASE_NOTES = [
  "Fnix Workbench: React + Tauri + Tailwind + Monaco.",
  "BYOK synced to ~/.fnix when agentd is running.",
  "Project rules: .fnix/rules.md and AGENTS.md.",
];

export const FNIX_CHANGELOG = [
  "1.0.0 — Fnix-native workbench (derived from MIT PunamIDE UI).",
  "Harness bridge: settings → agentd /api/v1/harness/config.",
  "Workspace ensure: opens create {workspace}/.fnix.",
];
