/**
 * Copyright (C) 2026 FnixAgent. All rights reserved.
 * Software Name: FnixAgent 智能工作台系统 V1.0
 * This software and its source code are proprietary and confidential.
 * Unauthorized copying, modification, distribution, or use is strictly prohibited.
 */

import { describe, expect, it } from "vitest";
import { normalizeThemePref, resolveShellTheme } from "../shell/desktop/theme";

describe("theme", () => {
  it("normalizes preference", () => {
    expect(normalizeThemePref("dark")).toBe("dark");
    expect(normalizeThemePref("light")).toBe("light");
    expect(normalizeThemePref("system")).toBe("system");
    expect(normalizeThemePref("weird")).toBe("system");
  });

  it("resolves explicit themes", () => {
    expect(resolveShellTheme("light")).toBe("light");
    expect(resolveShellTheme("dark")).toBe("dark");
  });
});
