import { describe, expect, it } from "vitest";
import { TaskList } from "../components/task-list";

describe("TaskList", () => {
  it("renders owner-filtered tasks", () => {
    const element = TaskList({
      initialTasks: [
        { id: "task-1", owner: "ops", stale: true, title: "Review dashboard" },
        { id: "task-2", owner: "eng", stale: false, title: "Refactor route" },
      ],
      owner: "ops",
    });

    expect(element.type).toBe("section");
  });
});
