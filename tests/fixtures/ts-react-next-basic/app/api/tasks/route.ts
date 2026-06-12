import { loadTasks } from "../../../lib/tasks.js";

export async function GET(): Promise<Response> {
  const tasks = await loadTasks("open");
  return Response.json({ tasks });
}
