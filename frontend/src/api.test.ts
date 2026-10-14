import { afterEach, describe, it, expect, vi } from "vitest";
import { api, post, setCsrf, scoreLabel, ApiError } from "./api";
afterEach(() => {
  vi.unstubAllGlobals();
  setCsrf("");
});
describe("authenticated API client", () => {
  it("sends CSRF on writes and preserves cookie credentials", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ id: 7 }), { status: 201 }),
      );
    vi.stubGlobal("fetch", fetch);
    setCsrf("session-csrf");
    await post("/tickets", { subject: "Test" });
    const options = fetch.mock.calls[0][1];
    expect(options.headers.get("X-CSRF-Token")).toBe("session-csrf");
    expect(options.credentials).toBe("same-origin");
    expect(options.body).toBe(JSON.stringify({ subject: "Test" }));
  });
  it("surfaces validation failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: [{ msg: "Subject is too short" }] }),
            { status: 422 },
          ),
        ),
    );
    await expect(post("/tickets", {})).rejects.toThrow("Subject is too short");
  });
  it("reports server connectivity without pretending to return data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    await expect(api("/tickets")).rejects.toBeInstanceOf(ApiError);
  });
  it("formats evidence scores without making a probability claim", () => {
    expect(scoreLabel(0.824)).toBe("82%");
    expect(scoreLabel(undefined)).toBe("—");
  });
});
