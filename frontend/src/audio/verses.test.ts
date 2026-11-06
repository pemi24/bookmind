import { describe, expect, it } from "vitest";
import type { ChapterSentence } from "../api";
import { verseStep, withAnnouncements, withOpening } from "./useBookPlayer";

type Item = { kind?: ChapterSentence["kind"]; chapterId: number; start: number; text: string };

/** A chapter with verses as the server sends it to read aloud: the announcement, then each verse's
 * number and text (every item of a verse has the verse's start). */
function chapter(chapterId: number, name: string, verses: number[]): Item[] {
  const items: Item[] = [{ kind: "chapter", chapterId, start: 0, text: `${name}.` }];
  verses.forEach((n, i) => {
    const start = i * 100;
    items.push({ kind: "verse-number", chapterId, start, text: `Verse ${n}.` });
    items.push({ kind: "text", chapterId, start, text: `Text of verse ${n}, first sentence.` });
    items.push({ kind: "text", chapterId, start, text: `Text of verse ${n}, second sentence.` });
  });
  return items;
}

const texts = (items: Item[]) => items.map((i) => i.text);

describe("withAnnouncements", () => {
  const john3 = chapter(7, "John, chapter 3", [1, 2]);

  it("keeps everything by default", () => {
    expect(withAnnouncements(john3, { verses: true, chapter: true })).toEqual(john3);
  });
  it("leaves out verse numbers", () => {
    expect(texts(withAnnouncements(john3, { verses: false, chapter: true }))).toEqual([
      "John, chapter 3.",
      "Text of verse 1, first sentence.",
      "Text of verse 1, second sentence.",
      "Text of verse 2, first sentence.",
      "Text of verse 2, second sentence.",
    ]);
  });
  it("leaves out the chapter announcement", () => {
    expect(texts(withAnnouncements(john3, { verses: true, chapter: false }))[0]).toBe("Verse 1.");
  });
  it("doesn't touch books without verses", () => {
    const plain: Item[] = [{ chapterId: 1, start: 0, text: "It was a dark and stormy night." }];
    expect(withAnnouncements(plain, { verses: false, chapter: false })).toEqual(plain);
  });
});

describe("withOpening (the chapter is announced once)", () => {
  const john3 = chapter(7, "John, chapter 3", [1, 2, 3]);

  it("announces the chapter before a verse in the middle", () => {
    const start = john3.findIndex((i) => i.text === "Verse 3.");
    const items = withOpening(john3, start);
    expect(texts(items.slice(start, start + 3))).toEqual(["John, chapter 3.", "Verse 3.", "Text of verse 3, first sentence."]);
    // played from `start`, the announcement comes once
    expect(texts(items.slice(start)).filter((t) => t === "John, chapter 3.")).toHaveLength(1);
  });
  it("adds nothing at the start of the chapter", () => {
    expect(withOpening(john3, 0)).toBe(john3);
  });
  it("adds nothing in a book without verses, or once into the next chapter", () => {
    const plain: Item[] = [
      { chapterId: 1, start: 0, text: "One." },
      { chapterId: 1, start: 5, text: "Two." },
    ];
    expect(withOpening(plain, 1)).toBe(plain);
    const two = [...john3, ...chapter(8, "John, chapter 4", [1])];
    const next = two.findIndex((i) => i.chapterId === 8);
    expect(withOpening(two, next)).toBe(two); // that chapter's own announcement is already there
  });
});

describe("verseStep (previous/next verse)", () => {
  const items = [...chapter(7, "John, chapter 3", [1, 2]), ...chapter(8, "John, chapter 4", [1])];
  const at = (text: string, chapterId = 7) => items.findIndex((i) => i.text === text && i.chapterId === chapterId);

  it("goes to the next verse's number, from anywhere in a verse", () => {
    expect(verseStep(items, at("Verse 1."), 1)).toBe(at("Verse 2."));
    expect(verseStep(items, at("Text of verse 1, second sentence."), 1)).toBe(at("Verse 2."));
  });
  it("goes from a chapter's last verse to the next chapter's announcement", () => {
    expect(verseStep(items, at("Text of verse 2, first sentence."), 1)).toBe(at("John, chapter 4.", 8));
  });
  it("goes back to the previous verse", () => {
    expect(verseStep(items, at("Text of verse 2, second sentence."), -1)).toBe(at("John, chapter 3."));
    expect(verseStep(items, at("Verse 1.", 8), -1)).toBe(at("Verse 2."));
  });
  it("stays in range", () => {
    expect(verseStep(items, 0, -1)).toBe(0);
    expect(verseStep(items, items.length - 1, 1)).toBe(-1);
  });
});
