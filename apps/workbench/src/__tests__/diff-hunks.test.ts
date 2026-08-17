/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { describe, expect, it } from "vitest";
import { applySelectedHunks, splitUnifiedHunks } from "../shell/chatgpt-desktop/diffHunks";

const SAMPLE = `@@ -1,3 +1,4 @@
 line1
-line2
+line2b
 line3
+line4
`;

describe("diffHunks", () => {
  it("parses unified hunks", () => {
    const hunks = splitUnifiedHunks(SAMPLE);
    expect(hunks).toHaveLength(1);
    expect(hunks[0].oldStart).toBe(1);
    expect(hunks[0].lines.some((l) => l.kind === "add" && l.text === "line2b")).toBe(true);
  });

  it("applies accepted hunks onto original", () => {
    const original = "line1\nline2\nline3";
    const hunks = splitUnifiedHunks(SAMPLE);
    const next = applySelectedHunks(original, hunks, [true]);
    expect(next).toBe("line1\nline2b\nline3\nline4\n");
  });

  it("keeps original when hunk rejected", () => {
    const original = "line1\nline2\nline3";
    const hunks = splitUnifiedHunks(SAMPLE);
    const next = applySelectedHunks(original, hunks, [false]);
    expect(next).toBe("line1\nline2\nline3");
  });
});
