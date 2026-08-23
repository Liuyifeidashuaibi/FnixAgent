/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { error, info } from '@tauri-apps/plugin-log';
import { SENTRY_DSN } from './config/alpha';

const INIT_FLAG = '__fnix_observability_init';

export function initObservability() {
  // Prevent duplicate initialization during HMR
  if ((window as any)[INIT_FLAG]) return;
  (window as any)[INIT_FLAG] = true;

  info('Fnix observability initialized').catch(() => {});

  window.addEventListener('error', (event) => {
    error(`UI error: ${event.message}`).catch(() => {});
  });

  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason instanceof Error ? event.reason.message : String(event.reason);
    error(`Unhandled promise rejection: ${reason}`).catch(() => {});
  });

  // Sentry is OPTIONAL: only initialized when SENTRY_DSN is configured.
  // FnixAgent ships with NO default Sentry DSN (local-first, no telemetry).
  // Users who opt-in to Sentry must set VITE_SENTRY_DSN in their environment.
  if (SENTRY_DSN) {
    import('@sentry/react')
      .then(({ default: Sentry }) => {
        Sentry.init({
          dsn: SENTRY_DSN,
          environment: import.meta.env.MODE,
          release: 'workbench@1.0.0',
          sendDefaultPii: false,
          tracesSampleRate: 0,
        });
      })
      .catch(() => {
        // @sentry/react not installed — Sentry is an optional dependency.
      });
  }
}
