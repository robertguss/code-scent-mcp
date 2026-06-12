import { TaskCard } from "./task-card.jsx";
import { useTasks } from "../hooks/useTasks";

export type Task = {
  readonly id: string;
  readonly owner: string;
  readonly stale: boolean;
  readonly title: string;
};

type TaskListProps = {
  readonly initialTasks: readonly Task[];
  readonly owner: string;
};

export function TaskList({ initialTasks, owner }: TaskListProps) {
  const { selectedId, selectTask, visibleTasks } = useTasks(initialTasks, owner);

  return (
    <section>
      <h1>Tasks</h1>
      {visibleTasks.map((task) => (
        <TaskCard key={task.id} task={task} onSelect={selectTask} />
      ))}
      <output>{selectedId ?? "none"}</output>
    </section>
  );
}
