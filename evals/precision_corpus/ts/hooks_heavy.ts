import { useMemo, useState } from "react";

export function useThing(seed: number) {
  const [count, setCount] = useState(seed);
  const doubled = useMemo(() => count * 2, [count]);
  return { doubled, setCount };
}
