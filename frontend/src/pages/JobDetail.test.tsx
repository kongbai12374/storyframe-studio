import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api, key } from "../api";
import JobDetail from "./JobDetail";

vi.mock("../api", async (original) => ({
  ...(await original<typeof import("../api")>()),
  api: vi.fn(),
  key: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("reuses the retry key after a lost response and blocks clicks during submission", async () => {
  vi.mocked(key).mockReturnValueOnce("00000000-0000-4000-8000-000000000001");
  vi.mocked(api)
    .mockResolvedValueOnce({ id: 9, status: "failed", result: {}, logs: [] })
    .mockRejectedValueOnce(new Error("连接中断"))
    .mockReturnValueOnce(new Promise(() => {}));
  render(
    <MemoryRouter initialEntries={["/jobs/9"]}>
      <Routes><Route path="/jobs/:id" element={<JobDetail />} /></Routes>
    </MemoryRouter>,
  );
  const button = await screen.findByRole("button", { name: "查询原任务 / 核查后重试" });
  fireEvent.click(button);
  await screen.findByText("连接中断");
  fireEvent.click(button);
  await waitFor(() => expect(button.hasAttribute("disabled")).toBe(true));
  fireEvent.click(button);
  const retry = ["jobs/9/retry/", "POST", { idempotency_key: "00000000-0000-4000-8000-000000000001" }];
  expect(vi.mocked(api).mock.calls.slice(1)).toEqual([retry, retry]);
  expect(key).toHaveBeenCalledTimes(1);
});
