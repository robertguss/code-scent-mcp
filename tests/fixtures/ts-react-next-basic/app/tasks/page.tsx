import { TaskList } from "../../components/task-list";
import { loadTasks } from "../../lib/tasks.js";

export default async function TasksPage() {
  const tasks = await loadTasks("open");
  return <TaskList initialTasks={tasks} owner="ops" />;
}
