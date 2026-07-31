import { describe, expect, it } from "vitest";
import { normalizeThemePref, resolveShellTheme } from "../shell/chatgpt-desktop/theme";

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
