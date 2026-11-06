import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("api requests with a body", () => {
  it("send it as JSON (the server reads only JSON bodies)", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true }), { status: 202, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetch);
    await api.setVerseMode(12, true);
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/api/books/12/verse-mode");
    expect(init.method).toBe("PUT");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init.body))).toEqual({ detect: true });
  });
});
