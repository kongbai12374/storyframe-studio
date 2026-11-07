import { useEffect, useState } from "react";
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    setError("");
    loader()
      .then((v) => {
        if (live) setData(v);
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [...deps, tick]);
  return { data, error, reload: () => setTick((x) => x + 1), setData };
}
export function usePoll<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let live = true,
      timer: ReturnType<typeof setTimeout>,
      failures = 0;
    async function run() {
      try {
        const d = await loader();
        if (live) {
          setData(d);
          setError("");
          failures = 0;
        }
      } catch (e) {
        if (live) {
          setError((e as Error).message);
          failures++;
        }
      } finally {
        if (live)
          timer = setTimeout(
            run,
            document.hidden ? 15000 : Math.min(3000 * 2 ** failures, 30000),
          );
      }
    }
    run();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, deps);
  return { data, error };
}
