import { useMemo, useState } from "react";
import type { Task } from "../components/task-list";

export function useTasks(initialTasks: readonly Task[], owner: string) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const visibleTasks = useMemo(
    () => initialTasks.filter((task) => task.owner === owner),
    [initialTasks, owner],
  );

  return {
    selectTask: setSelectedId,
    selectedId,
    visibleTasks,
  };
}
