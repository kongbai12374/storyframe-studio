import { it, expect, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePoll } from "./hooks";
it("clears polling timer when leaving page", async () => {
  vi.useFakeTimers();
  const loader = vi.fn().mockResolvedValue({ ok: true });
  const { unmount } = renderHook(() => usePoll(loader));
  await act(async () => {
    await Promise.resolve();
  });
  expect(loader).toHaveBeenCalledTimes(1);
  unmount();
  await act(async () => {
    vi.advanceTimersByTime(30000);
  });
  expect(loader).toHaveBeenCalledTimes(1);
  vi.useRealTimers();
});
