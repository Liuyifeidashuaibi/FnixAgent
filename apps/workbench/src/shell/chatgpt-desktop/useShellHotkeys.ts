/**
 * Shell keyboard shortcuts (WCAG 2.2 keyboard operable).
 * - Escape: close review / settings overlays (caller-provided)
 * - Ctrl/Cmd+Enter: Accept all (when review open)
 * - Ctrl/Cmd+Shift+Enter: Accept current file
 * - Ctrl/Cmd+Z: Undo last changeset (when available)
 */

import { useEffect } from "react";

export type ShellHotkeyHandlers = {
  enabled?: boolean;
  reviewOpen?: boolean;
  canAccept?: boolean;
  canAcceptFile?: boolean;
  canUndo?: boolean;
  onCloseReview?: () => void;
  onAcceptAll?: () => void;
  onAcceptFile?: () => void;
  onUndo?: () => void;
  /** Focus main composer / feed */
  onSkipToMain?: () => void;
};

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  if (tag === "TEXTAREA" || tag === "INPUT" || tag === "SELECT") return true;
  if (el.isContentEditable) return true;
  return false;
}

export function useShellHotkeys(h: ShellHotkeyHandlers) {
  useEffect(() => {
    if (h.enabled === false) return;

    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;

      if (e.key === "Escape" && h.reviewOpen) {
        e.preventDefault();
        h.onCloseReview?.();
        return;
      }

      // Skip to main: Alt+/ (when not typing)
      if (e.altKey && e.key === "/" && !isTypingTarget(e.target)) {
        e.preventDefault();
        h.onSkipToMain?.();
        return;
      }

      if (!h.reviewOpen || !mod) return;

      if (e.key === "Enter" && e.shiftKey && h.canAcceptFile) {
        e.preventDefault();
        h.onAcceptFile?.();
        return;
      }
      if (e.key === "Enter" && !e.shiftKey && h.canAccept) {
        e.preventDefault();
        h.onAcceptAll?.();
        return;
      }
      if ((e.key === "z" || e.key === "Z") && !e.shiftKey && h.canUndo) {
        // Don't steal browser undo while typing in composer
        if (isTypingTarget(e.target)) return;
        e.preventDefault();
        h.onUndo?.();
      }
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    h.enabled,
    h.reviewOpen,
    h.canAccept,
    h.canAcceptFile,
    h.canUndo,
    h.onCloseReview,
    h.onAcceptAll,
    h.onAcceptFile,
    h.onUndo,
    h.onSkipToMain,
  ]);
}
