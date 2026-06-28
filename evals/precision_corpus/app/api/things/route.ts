export async function GET(): Promise<Response> {
  const things = ["one", "two", "three"];
  const payload = { things, count: things.length };
  return Response.json(payload);
}
