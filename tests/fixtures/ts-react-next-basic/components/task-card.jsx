export function TaskCard({ task, onSelect }) {
  const staleClassName = task.stale ? "task-card task-card--stale" : "task-card";

  return (
    <article className={staleClassName}>
      <button type="button" onClick={() => onSelect(task.id)}>
        {task.title}
      </button>
      <p>{task.owner}</p>
    </article>
  );
}
