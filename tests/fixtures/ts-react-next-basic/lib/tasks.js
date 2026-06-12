const TASKS = [
  { id: "task-1", owner: "ops", stale: true, title: "Review dashboard" },
  { id: "task-2", owner: "eng", stale: false, title: "Refactor route" },
];

export async function loadTasks(status) {
  return TASKS.filter((task) => status === "open" || task.stale);
}
