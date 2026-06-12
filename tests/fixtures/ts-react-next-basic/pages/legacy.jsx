import { TaskCard } from "../components/task-card.jsx";

export default function LegacyTasksPage({ tasks }) {
  return (
    <main>
      {tasks.map((task) => (
        <TaskCard key={task.id} task={task} onSelect={() => undefined} />
      ))}
    </main>
  );
}
