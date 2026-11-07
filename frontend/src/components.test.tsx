import React from "react";
import { it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { Pager, ErrorBox, Empty } from "./components";
afterEach(cleanup);
it("paginates and disables previous on first page", () => {
  const change = vi.fn();
  render(<Pager page={1} total={21} onChange={change} />);
  expect(
    screen.getByRole("button", { name: "上一页" }).hasAttribute("disabled"),
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "下一页" }));
  expect(change).toHaveBeenCalledWith(2);
});
it("announces errors without HTML execution", () => {
  render(<ErrorBox error={"<script>test</script>"} />);
  expect(screen.getByRole("alert").textContent).toBe("<script>test</script>");
});
it("renders empty state", () => {
  render(<Empty text="没有素材" />);
  expect(screen.getByRole("heading").textContent).toBe("没有素材");
});
