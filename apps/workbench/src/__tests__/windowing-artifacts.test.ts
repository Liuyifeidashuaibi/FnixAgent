import { describe, expect, it } from "vitest";
import { softTruncate, windowMessages } from "../shell/chatgpt-desktop/windowing";
import {
  assessArtifactQuality,
  deliverableCoverage,
  formatArtifactVersion,
} from "../shell/chatgpt-desktop/artifactMeta";

describe("windowing", () => {
  it("windows long message lists", () => {
    const items = Array.from({ length: 60 }, (_, i) => i);
    const { visible, hidden } = windowMessages(items, 48);
    expect(hidden).toBe(12);
    expect(visible).toHaveLength(48);
    expect(visible[0]).toBe(12);
  });

  it("soft-truncates long content", () => {
    const text = "a".repeat(20_000);
    const r = softTruncate(text, 12_000);
    expect(r.truncated).toBe(true);
    expect(r.text.length).toBeLessThanOrEqual(12_000);
  });
});

describe("artifactMeta", () => {
  it("marks office/html as ready", () => {
    expect(assessArtifactQuality(".fnix/artifacts/a/index.html")).toBe("ready");
    expect(assessArtifactQuality("report.docx")).toBe("ready");
    expect(assessArtifactQuality("bin.xyz")).toBe("check");
  });

  it("scores deliverable coverage", () => {
    const cov = deliverableCoverage(
      [{ path: ".fnix/artifacts/memo/notes.md" }],
      ["memo", "notes.md"],
    );
    expect(cov).toBe(100);
  });

  it("formats version", () => {
    expect(formatArtifactVersion(undefined)).toBe("v1");
    expect(formatArtifactVersion(Date.now())).toContain("v1");
  });
});
