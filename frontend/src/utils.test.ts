import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Book } from "./types";
import { applyTheme, coverGradient, findLoose, formatBytes, formatDate, isIndexing, loadPref, savePref, spoilerLimit } from "./utils";

describe("formatBytes", () => {
  it("uses B, KB and MB", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1023)).toBe("1023 B");
    expect(formatBytes(1024)).toBe("1 KB");
    expect(formatBytes(1536 * 1024)).toBe("1.5 MB");
  });
});

describe("formatDate", () => {
  it("is empty for no date", () => {
    expect(formatDate(null)).toBe("");
    expect(formatDate("")).toBe("");
  });
  it("formats a date with the year", () => {
    expect(formatDate("2024-03-15T12:00:00Z")).toContain("2024");
  });
});

describe("coverGradient", () => {
  it("is deterministic and depends on the seed", () => {
    expect(coverGradient("Dune")).toBe(coverGradient("Dune"));
    expect(coverGradient("Dune")).not.toBe(coverGradient("Emma"));
    expect(coverGradient("Dune")).toMatch(/^linear-gradient\(145deg, hsl\(\d+ 55% 42%\), hsl\(\d+ 60% 28%\)\)$/);
  });
});

describe("isIndexing", () => {
  it("is true while the book is pending or processing", () => {
    expect(isIndexing("pending")).toBe(true);
    expect(isIndexing("processing")).toBe(true);
    expect(isIndexing("ready")).toBe(false);
    expect(isIndexing("failed")).toBe(false);
  });
});

describe("loadPref / savePref", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.restoreAllMocks());

  it("round-trips JSON values", () => {
    savePref("k", { a: 1, b: [true] });
    expect(loadPref("k", null)).toEqual({ a: 1, b: [true] });
  });
  it("falls back when missing or unreadable", () => {
    expect(loadPref("missing", 7)).toBe(7);
    localStorage.setItem("bad", "{not json");
    expect(loadPref("bad", "x")).toBe("x");
  });
  it("ignores storage errors", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("denied");
    });
    expect(() => savePref("k", 1)).not.toThrow();
    expect(loadPref("k", 2)).toBe(2);
  });
});

describe("findLoose", () => {
  it("finds an exact match", () => {
    expect(findLoose("Call me Ishmael.", "me Ishmael")).toEqual([5, 15]);
  });
  it("ignores case, whitespace runs and quote/dash styles", () => {
    const hay = "He said “Hello—there”  and\n left.";
    const [s, e] = findLoose(hay, '"hello-there" and left')!;
    expect(hay.slice(s, e)).toBe("“Hello—there”  and\n left");
  });
  it("prefers the occurrence nearest to `near`", () => {
    const hay = "the cat sat. the cat sat. the cat sat.";
    expect(findLoose(hay, "the cat", 0)).toEqual([0, 7]);
    expect(findLoose(hay, "the cat", 14)).toEqual([13, 20]);
    expect(findLoose(hay, "the cat", 100)).toEqual([26, 33]);
  });
  it("returns null for no match or a too-short needle", () => {
    expect(findLoose("abc", "xyz")).toBeNull();
    expect(findLoose("abc", "a")).toBeNull();
    expect(findLoose("abc", "   ")).toBeNull();
  });
});

describe("spoilerLimit", () => {
  const book = (furthest?: number) => ({ id: 3, reading: furthest === undefined ? null : { furthest } }) as unknown as Book;
  beforeEach(() => localStorage.clear());

  it("is off by default", () => {
    expect(spoilerLimit(book(4))).toBeNull();
  });
  it("uses a fixed chapter or follows the furthest one read", () => {
    expect(spoilerLimit(book(4), 2)).toBe(2);
    expect(spoilerLimit(book(4), "follow")).toBe(4);
    expect(spoilerLimit(book(), "follow")).toBe(1);
  });
  it("reads the saved setting for the book", () => {
    savePref("spoiler:3", "follow");
    expect(spoilerLimit(book(5))).toBe(5);
  });
});

describe("applyTheme", () => {
  const darkQuery = (matches: boolean) =>
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches })),
    );
  beforeEach(() => localStorage.clear());
  afterEach(() => vi.unstubAllGlobals());

  it("applies and remembers an explicit theme", () => {
    darkQuery(false);
    applyTheme("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBe("dark");
    applyTheme("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("theme")).toBe("light");
  });
  it("follows the device and forgets the saved theme", () => {
    localStorage.setItem("theme", "light");
    darkQuery(true);
    applyTheme("system");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("theme")).toBeNull();
  });
});
