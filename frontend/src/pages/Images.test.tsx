import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api } from "../api";
import Images from "./Images";

vi.mock("../api", () => ({ api: vi.fn(), key: () => "image-request-1" }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

it("submits the chosen image provider once and opens the job", async () => {
  vi.mocked(api)
    .mockResolvedValueOnce([{ id: 7, name: "示例", model: "模型", service: "image", active: true }])
    .mockResolvedValueOnce({ id: 42 });
  render(
    <MemoryRouter initialEntries={["/images"]}>
      <Routes>
        <Route path="/images" element={<Images />} />
        <Route path="/jobs/42" element={<h1>任务 42</h1>} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("option", { name: "示例 · 模型" });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "7" } });
  fireEvent.change(screen.getByLabelText("画面提示词"), { target: { value: "湖面" } });
  fireEvent.click(screen.getByRole("button", { name: "生成图片 →" }));
  await screen.findByRole("heading", { name: "任务 42" });
  expect(vi.mocked(api).mock.calls).toEqual([
    ["providers/"],
    ["jobs/", "POST", {
      kind: "image_api", provider_id: 7, prompt: "湖面", size: "1024x1024",
      count: 1, idempotency_key: "image-request-1",
    }],
  ]);
});
