/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { describe, expect, it } from "vitest";
import { assessFileReviewRisk, assessReviewBatch } from "../shell/chatgpt-desktop/reviewRisk";

describe("reviewRisk", () => {
  it("flags sensitive paths as high", () => {
    const r = assessFileReviewRisk({
      path: ".env",
      action: "modify",
      content: "SECRET=1\n",
    });
    expect(r.level).toBe("high");
    expect(r.reasons.some((x) => x.includes("sensitive"))).toBe(true);
  });

  it("flags conflict markers", () => {
    const r = assessFileReviewRisk({
      path: "a.ts",
      content: "<<<<<<< HEAD\na\n=======\nb\n>>>>>>> theirs\n",
    });
    expect(r.hasConflict).toBe(true);
    expect(r.level).toBe("high");
  });

  it("batch max level", () => {
    const batch = assessReviewBatch([
      { path: "ok.ts", content: "const x = 1\n" },
      { path: "secrets/token", content: "x" },
    ]);
    expect(batch.maxLevel).toBe("high");
  });
});
