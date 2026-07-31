import { describe, expect, it } from "vitest";
import { ndjsonEventToBlock, redactSensitiveText } from "../utils/structuredBlocks";

describe("structured event blocks", () => {
  it("reads Codex step data from the nested step payload", () => {
    expect(ndjsonEventToBlock({
      type: "step_start",
      step: { step: 3, total: 5, description: "Run focused tests" },
    })).toEqual({
      kind: "progress",
      currentStep: 3,
      totalSteps: 5,
      description: "Run focused tests",
      isComplete: false,
    });
  });

  it("redacts credentials before rendering tool parameters", () => {
    const block = ndjsonEventToBlock({
      type: "action",
      content: {
        name: "fetch",
        args: { authorization: "Bearer private-token", api_key: "sk-supersecret123456" },
      },
    });

    expect(block?.kind).toBe("tool_call");
    if (block?.kind === "tool_call") {
      expect(block.params).not.toContain("private-token");
      expect(block.params).not.toContain("sk-supersecret");
      expect(block.params).toContain("[REDACTED]");
    }
  });

  it("redacts bearer tokens in free-form output", () => {
    expect(redactSensitiveText("Authorization: Bearer abc.def.ghi")).toBe(
      "Authorization: Bearer [REDACTED]",
    );
  });
});
