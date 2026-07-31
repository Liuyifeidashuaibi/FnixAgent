import * as Sentry from "@sentry/react";
import { error, info } from "@tauri-apps/plugin-log";
import { SENTRY_DSN } from "./config/alpha";

const INIT_FLAG = "__fnix_observability_init";

export function initObservability() {
  // Prevent duplicate initialization during HMR
  if ((window as any)[INIT_FLAG]) return;
  (window as any)[INIT_FLAG] = true;

  info("Fnix observability initialized").catch(() => {});

  window.addEventListener("error", (event) => {
    error(`UI error: ${event.message}`).catch(() => {});
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason instanceof Error ? event.reason.message : String(event.reason);
    error(`Unhandled promise rejection: ${reason}`).catch(() => {});
  });

  if (SENTRY_DSN) {
    Sentry.init({
      dsn: SENTRY_DSN,
      environment: import.meta.env.MODE,
      release: "workbench@1.0.0",
      sendDefaultPii: false,
      tracesSampleRate: 0,
    });
  }
}
