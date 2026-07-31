/**
 * Split unified diffs into hunks and apply a subset onto original content.
 */

type HunkLineKind = "add" | "del" | "ctx" | "meta";

interface HunkLine {
  kind: HunkLineKind;
  text: string;
}

export interface DiffHunk {
  index: number;
  header: string;
  oldStart: number;
  newStart: number;
  lines: HunkLine[];
}

export function splitUnifiedHunks(raw: string): DiffHunk[] {
  const text = (raw || "").replace(/\r\n/g, "\n");
  if (!text.trim()) return [];

  const lines = text.split("\n");
  const isUnified = lines.some(
    (l) => l.startsWith("@@") || l.startsWith("--- ") || l.startsWith("+++ "),
  );
  if (!isUnified) {
    // Whole-file create / plain content → single synthetic hunk
    return [
      {
        index: 0,
        header: "@@ full file @@",
        oldStart: 1,
        newStart: 1,
        lines: lines.map((t) => ({ kind: "add" as const, text: t })),
      },
    ];
  }

  const hunks: DiffHunk[] = [];
  let current: DiffHunk | null = null;

  for (const line of lines) {
    if (line.startsWith("@@")) {
      const m = line.match(/@@\s*-(\d+)(?:,\d+)?\s*\+(\d+)/);
      current = {
        index: hunks.length,
        header: line,
        oldStart: m ? Number(m[1]) : 1,
        newStart: m ? Number(m[2]) : 1,
        lines: [],
      };
      hunks.push(current);
      continue;
    }
    if (
      line.startsWith("---") ||
      line.startsWith("+++") ||
      line.startsWith("diff ") ||
      line.startsWith("index ")
    ) {
      continue;
    }
    if (!current) continue;
    if (line.startsWith("+")) {
      current.lines.push({ kind: "add", text: line.slice(1) });
    } else if (line.startsWith("-")) {
      current.lines.push({ kind: "del", text: line.slice(1) });
    } else {
      const body = line.startsWith(" ") ? line.slice(1) : line;
      current.lines.push({ kind: "ctx", text: body });
    }
  }
  return hunks;
}

/** Apply accepted hunks onto original; rejected hunks keep original lines. */
export function applySelectedHunks(
  original: string,
  hunks: DiffHunk[],
  accepted: boolean[],
): string {
  const origLines = original.replace(/\r\n/g, "\n").split("\n");
  // Drop trailing empty from split if original ended without newline? keep as-is.
  const result: string[] = [];
  let oi = 0;

  for (let h = 0; h < hunks.length; h++) {
    const hunk = hunks[h];
    const take = accepted[h] === true;
    const hunkOldStart = Math.max(0, hunk.oldStart - 1);

    while (oi < hunkOldStart && oi < origLines.length) {
      result.push(origLines[oi]);
      oi += 1;
    }

    const removeCount = hunk.lines.filter((l) => l.kind === "del" || l.kind === "ctx").length;

    if (take) {
      for (const l of hunk.lines) {
        if (l.kind === "add" || l.kind === "ctx") {
          result.push(l.text);
        }
      }
      oi += removeCount;
    } else {
      for (let k = 0; k < removeCount; k++) {
        if (oi < origLines.length) {
          result.push(origLines[oi]);
          oi += 1;
        }
      }
    }
  }

  while (oi < origLines.length) {
    result.push(origLines[oi]);
    oi += 1;
  }
  return result.join("\n");
}
