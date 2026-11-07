import { describe, it, expect, vi, afterEach } from "vitest";
import { api, scene, statuses } from "./api";
afterEach(() => vi.unstubAllGlobals());
describe("API and editor defaults", () => {
  it("makes independent scene values", () => {
    const a = scene(),
      b = scene();
    a.duration = 10;
    expect(b.duration).toBe(5);
    expect(b.image_id).toBeNull();
  });
  it("attaches CSRF to writes", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce({ json: async () => ({ csrfToken: "synthetic" }) })
      .mockResolvedValueOnce({
        status: 200,
        ok: true,
        json: async () => ({ ok: true }),
      });
    vi.stubGlobal("fetch", fetch);
    expect(await api("test/", "POST", { x: 1 })).toEqual({ ok: true });
    expect(fetch.mock.calls[1][1].headers["X-CSRFToken"]).toBe("synthetic");
  });
  it("shows field errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue({
          status: 400,
          ok: false,
          json: async () => ({ title: ["必填"] }),
        }),
    );
    await expect(api("test/")).rejects.toThrow("title: 必填");
  });
  it("maps terminal task states", () => {
    expect(statuses.interrupted).toBe("已中断");
    expect(statuses.succeeded).toBe("已完成");
  });
});
