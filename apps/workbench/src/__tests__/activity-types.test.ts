import { describe, expect, it } from "vitest";
import { finishRunning, upsertActivity, type ActivityItem } from "../shell/chatgpt-desktop/activityTypes";

const running: ActivityItem = {
  id: "tool-call-1",
  kind: "read",
  title: "读取 src/app.ts",
  path: "src/app.ts",
  meta: "read_file",
  status: "running",
  startedAt: 100,
};

describe("activity projection", () => {
  it("closes a tool call by stable id without losing its semantic title", () => {
    const next = upsertActivity([running], {
      id: "tool-call-1",
      kind: "tool",
      title: "read_file 已完成",
      meta: "read_file",
      status: "done",
      detail: "42 lines",
      startedAt: 200,
      endedAt: 300,
    });

    expect(next).toHaveLength(1);
    expect(next[0]).toMatchObject({
      kind: "read",
      title: "读取 src/app.ts",
      status: "done",
      detail: "42 lines",
      startedAt: 100,
      endedAt: 300,
    });
  });

  it("keeps user cancellation separate from execution failure", () => {
    expect(finishRunning([running], "cancelled")[0]?.status).toBe("cancelled");
  });
});
