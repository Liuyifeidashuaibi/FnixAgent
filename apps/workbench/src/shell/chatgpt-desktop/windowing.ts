/**
 * Transcript / diff windowing helpers — keep UI responsive at 500+ turns.
 */

export const MESSAGE_WINDOW = 48;
export const CONTENT_SOFT_LIMIT = 12_000;
export const DIFF_PAGE_LINES = 160;

/** Keep the latest N messages; return how many were hidden. */
export function windowMessages<T>(items: T[], windowSize = MESSAGE_WINDOW): {
  visible: T[];
  hidden: number;
} {
  if (items.length <= windowSize) return { visible: items, hidden: 0 };
  const hidden = items.length - windowSize;
  return { visible: items.slice(hidden), hidden };
}

/** Soft-truncate long assistant/user text for first paint. */
export function softTruncate(text: string, limit = CONTENT_SOFT_LIMIT): {
  text: string;
  truncated: boolean;
} {
  if (!text || text.length <= limit) return { text: text || "", truncated: false };
  // Prefer breaking at paragraph boundary near the limit
  let cut = text.lastIndexOf("\n\n", limit);
  if (cut < limit * 0.6) cut = limit;
  return { text: text.slice(0, cut), truncated: true };
}
