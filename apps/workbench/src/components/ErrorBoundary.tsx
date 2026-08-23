/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";
import { logger } from "./Logger";
import { APP_NAME, DEFAULT_PANEL_ERROR_MESSAGE, UNKNOWN_PANEL_ERROR_MESSAGE, FULL_APP_ERROR_MESSAGE, DEFAULT_ERROR_DESCRIPTION, RELOAD_BUTTON_TEXT } from "../lib/constants";
import { FNIX_DISCORD_URL } from "../config/alpha";

interface Props {
  children: ReactNode;
  fallbackLabel?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/** Panel-level error boundary — catches errors in a section without crashing the whole app */
export class PanelErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    logger.error(`[${APP_NAME} Panel Error] ${this.props.fallbackLabel || UNKNOWN_PANEL_ERROR_MESSAGE}:`, { error, componentStack: info.componentStack });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          gap: 12,
          color: "var(--muted, #6b7280)",
          fontSize: 13,
          textAlign: "center",
          height: "100%",
        }}>
          <span style={{ fontSize: 24 }}>⚠️</span>
          <p><strong>{this.props.fallbackLabel || DEFAULT_PANEL_ERROR_MESSAGE} crashed</strong></p>
          <p style={{ fontSize: 11, opacity: 0.7 }}>{this.state.error?.message?.slice(0, 100)}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "6px 14px",
              border: "1px solid var(--border, rgba(0,0,0,0.10))",
              borderRadius: 6,
              background: "transparent",
              color: "var(--text, #111827)",
              fontSize: 12,
              cursor: "pointer",
            }}
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

/** Full-app error boundary — shows reload screen */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    logger.error(FULL_APP_ERROR_MESSAGE, { error, componentStack: info.componentStack });
  }

  private getErrorText() {
    return [
      "Fnix error report",
      this.state.error?.message || "Unknown error",
      this.state.error?.stack || "",
    ].join("\n\n");
  }

  private copyError = async () => {
    await navigator.clipboard.writeText(this.getErrorText());
  };

  private exportLogs = async () => {
    try {
      const [{ save }, { invoke }] = await Promise.all([
        import("@tauri-apps/plugin-dialog"),
        import("@tauri-apps/api/core"),
      ]);
      const report = await invoke<string>("generate_diagnostics_report", {
        includeProjectPath: false,
        userMessage: this.getErrorText(),
      });
      const path = await save({
        defaultPath: "fnix-crash-diagnostics.txt",
        filters: [{ name: "Text", extensions: ["txt"] }],
      });
      if (path) {
        await invoke("export_diagnostics_report", { path, report });
      }
    } catch {
      // Browser mode or Tauri unavailable — copy error to clipboard as fallback
      await navigator.clipboard.writeText(this.getErrorText()).catch(() => {});
    }
  };

  private openDiscord = async () => {
    const { open } = await import("@tauri-apps/plugin-shell");
    await open(FNIX_DISCORD_URL);
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          height: "100vh",
          background: "var(--bg, #ffffff)",
          color: "var(--text, #111827)",
          fontFamily: "system-ui, sans-serif",
          padding: 32,
          textAlign: "center",
        }}>
          <h1 style={{ fontSize: 24, marginBottom: 16, color: "#dc2626" }}>
            Oops! Something went wrong.
          </h1>
          <p style={{ fontSize: 14, color: "#6b7280", maxWidth: 500, marginBottom: 24 }}>
            {DEFAULT_ERROR_DESCRIPTION}
          </p>
          <pre style={{
            fontSize: 12,
            color: "#dc2626",
            background: "var(--bg-soft, #f9fafb)",
            border: "1px solid #e5e7eb",
            padding: 16,
            borderRadius: 8,
            maxWidth: 600,
            overflow: "auto",
            marginBottom: 24,
          }}>
            {this.state.error?.message}
          </pre>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "center" }}>
            <button onClick={this.copyError} style={errorButtonStyle}>Copy Error</button>
            <button onClick={this.exportLogs} style={errorButtonStyle}>Export Logs</button>
            <button onClick={this.openDiscord} style={errorButtonStyle}>Open Discord</button>
            <button
              onClick={() => window.location.reload()}
              style={{
                ...errorButtonStyle,
                background: "#4f46e5",
                color: "#ffffff",
                border: "none",
                fontWeight: 600,
              }}
            >
              {RELOAD_BUTTON_TEXT}
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

const errorButtonStyle = {
  padding: "10px 16px",
  background: "#f3f4f6",
  color: "#111827",
  border: "1px solid #e5e7eb",
  borderRadius: 8,
  fontSize: 13,
  cursor: "pointer",
};
