import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { publicRouteFromHash } from "../Root";
import AuthShowcase from "./AuthShowcase";
import * as content from "./content";
import Landing from "./Landing";
import { Accordion } from "./ui/kit";
import { useTyping } from "./ui/typing";

/** jsdom has no matchMedia; `reduce` decides whether reduced motion is on. */
function mockMotion(reduce: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: reduce && query.includes("reduce"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  localStorage.clear();
  mockMotion(true);
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe("landing page", () => {
  it("renders every section, with one h1 and semantic landmarks", () => {
    render(<Landing />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe(content.hero.headline);
    for (const title of [
      content.showcase.title,
      content.highlights.title,
      content.howItWorks.title,
      content.capabilities.title,
      content.useCases.title,
      content.testimonials.title,
      content.faq.title,
      content.closing.title,
    ]) {
      expect(screen.getByRole("heading", { level: 2, name: title })).toBeTruthy();
    }
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("contentinfo")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeTruthy();
  });

  it("links: section anchors exist, and sign-up / log-in open the auth pages", () => {
    const { container } = render(<Landing />);
    const anchors = [...container.querySelectorAll<HTMLAnchorElement>("a[href^='#']")].map((a) => a.getAttribute("href")!);
    for (const href of anchors.filter((h) => !h.startsWith("#/") && h !== "#")) {
      expect(container.querySelector(href), `${href} has a target`).not.toBeNull();
    }
    const cta = screen.getAllByRole("link", { name: /get started free/i });
    expect(cta.length).toBeGreaterThanOrEqual(3);
    expect(cta.every((a) => a.getAttribute("href") === "#/signup")).toBe(true);
    expect(screen.getAllByRole("link", { name: /^log in$/i })[0].getAttribute("href")).toBe("#/login");
    // every "Try this" goes to sign-up
    for (const a of screen.getAllByRole("link", { name: /try this/i })) expect(a.getAttribute("href")).toBe(content.useCases.tryHref);
  });

  it("section links scroll smoothly instead of changing the route", () => {
    render(<Landing />);
    const link = within(screen.getByRole("navigation", { name: "Main" })).getAllByRole("link", { name: "FAQ" })[0];
    const ev = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
    link.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    expect(window.location.hash).not.toBe("#faq");
  });

  it("the announcement can be dismissed, and stays dismissed", () => {
    const { unmount } = render(<Landing />);
    expect(screen.getByRole("region", { name: "What's new" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /dismiss announcement/i }));
    expect(screen.queryByRole("region", { name: "What's new" })).toBeNull();
    unmount();
    render(<Landing />);
    expect(screen.queryByRole("region", { name: "What's new" })).toBeNull();
  });

  it("mobile menu: toggles, and Escape closes it", () => {
    render(<Landing />);
    const button = screen.getByRole("button", { name: /open menu/i });
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById("mobile-menu")!.hidden).toBe(false);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(button);
  });

  it("showcase tabs: arrow keys move between audiences, and the panel follows", () => {
    render(<Landing />);
    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(content.showcase.tabs.map((t) => t.label));
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(tabs[0], { key: "ArrowRight" });
    const now = screen.getAllByRole("tab");
    expect(now[1].getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(now[1]);
    const panel = screen.getByRole("tabpanel");
    expect(panel.getAttribute("aria-labelledby")).toBe(now[1].id);
    expect(panel.textContent).toContain(content.showcase.tabs[1].ask);
    fireEvent.keyDown(now[1], { key: "End" });
    expect(screen.getAllByRole("tab").at(-1)!.getAttribute("aria-selected")).toBe("true");
  });

  it("use cases can be filtered by audience", () => {
    render(<Landing />);
    const all = content.useCases.cards.length;
    const list = () => screen.getByRole("heading", { level: 2, name: content.useCases.title }).closest("section")!;
    expect(within(list()).getAllByRole("link", { name: /try this/i })).toHaveLength(all);
    fireEvent.click(screen.getByRole("button", { name: "Writers" }));
    const writers = content.useCases.cards.filter((c) => c.audiences.includes("writers"));
    expect(within(list()).getAllByRole("link", { name: /try this/i })).toHaveLength(writers.length);
    expect(screen.getByRole("button", { name: "Writers" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("sample testimonials are labelled as samples", () => {
    render(<Landing />);
    expect(screen.getAllByText("Sample")).toHaveLength(content.testimonials.sample ? content.testimonials.items.length : 0);
  });
});

describe("accordion", () => {
  it("opens one answer at a time, with matching ARIA state", () => {
    render(<Accordion items={content.faq.items} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons[0].getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(buttons[1]);
    expect(buttons[1].getAttribute("aria-expanded")).toBe("true");
    expect(buttons[0].getAttribute("aria-expanded")).toBe("false");
    const answer = document.getElementById(buttons[1].getAttribute("aria-controls")!)!;
    expect(answer.hidden).toBe(false);
    expect(answer.textContent).toBe(content.faq.items[1].a);
    fireEvent.click(buttons[1]);
    expect(answer.hidden).toBe(true);
  });
});

describe("typing demo", () => {
  function Typed({ text, start }: { text: string; start: boolean }) {
    const { typed, done } = useTyping(text, start, { delay: 10 });
    return <p data-done={done}>{typed}</p>;
  }

  it("shows the whole text at once with reduced motion", () => {
    mockMotion(true);
    render(<Typed text="Curiosity, mostly." start />);
    expect(screen.getByText("Curiosity, mostly.").dataset.done).toBe("true");
  });

  it("types word by word otherwise, and only once started", () => {
    vi.useFakeTimers();
    try {
      mockMotion(false);
      const { rerender, container } = render(<Typed text="Curiosity, mostly. She runs after it." start={false} />);
      expect(container.textContent).toBe("");
      rerender(<Typed text="Curiosity, mostly. She runs after it." start />);
      act(() => void vi.advanceTimersByTime(20));
      expect(container.textContent).toBe("Curiosity,");
      act(() => void vi.advanceTimersByTime(5000));
      expect(container.textContent).toBe("Curiosity, mostly. She runs after it.");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("content config", () => {
  it("has the FAQ topics the page promises", () => {
    const qs = content.faq.items.map((i) => i.q.toLowerCase()).join(" | ");
    for (const topic of ["file types", "see my books", "offline", "accurate", "languages", "cost"]) expect(qs).toContain(topic);
  });

  it("uses known audiences, unique ids, and citation markers that have sources", () => {
    const filters = new Set(content.useCases.filters.map((f) => f.id));
    for (const c of content.useCases.cards) for (const a of c.audiences) expect(filters.has(a)).toBe(true);
    const ids = [
      content.showcase.id,
      content.highlights.id,
      content.howItWorks.id,
      content.capabilities.id,
      content.useCases.id,
      content.testimonials.id,
      content.faq.id,
      ...content.highlights.rows.map((r) => r.id),
    ];
    expect(new Set(ids).size).toBe(ids.length);
    const markers = [...content.heroChat.answer.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1]));
    expect(markers.every((m) => content.heroChat.citations.some((c) => c.marker === m))).toBe(true);
    expect(content.capabilities.groups).toHaveLength(6);
    expect(content.pillars).toHaveLength(3);
  });
});

describe("routing for signed-out visitors", () => {
  it("sends #/ and section anchors to the landing page, and auth paths to the forms", () => {
    expect(publicRouteFromHash("")).toBe("landing");
    expect(publicRouteFromHash("#/")).toBe("landing");
    expect(publicRouteFromHash("#faq")).toBe("landing");
    expect(publicRouteFromHash("#/login")).toBe("auth");
    expect(publicRouteFromHash("#/signup")).toBe("auth");
    expect(publicRouteFromHash("#/reset?token=abc")).toBe("auth");
    expect(publicRouteFromHash("#/verify?token=abc")).toBe("auth");
    expect(publicRouteFromHash("#/privacy")).toBe("privacy");
    expect(publicRouteFromHash("#/terms")).toBe("terms");
  });
});

describe("sign-in slideshow", () => {
  const current = () => screen.getAllByRole("group").find((g) => g.getAttribute("aria-hidden") === "false")!;
  const slides = content.authShowcase.slides;

  it("advances on its own, and the pause button stops it", () => {
    vi.useFakeTimers();
    try {
      mockMotion(false);
      render(<AuthShowcase />);
      expect(current().getAttribute("aria-label")).toContain(slides[0].title);
      act(() => void vi.advanceTimersByTime(content.authShowcase.intervalMs));
      expect(current().getAttribute("aria-label")).toContain(slides[1].title);
      fireEvent.click(screen.getByRole("button", { name: /pause slideshow/i }));
      act(() => void vi.advanceTimersByTime(content.authShowcase.intervalMs * 3));
      expect(current().getAttribute("aria-label")).toContain(slides[1].title);
      expect(screen.getByRole("button", { name: /play slideshow/i })).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("never moves by itself with reduced motion, but the controls still work", () => {
    vi.useFakeTimers();
    try {
      mockMotion(true);
      render(<AuthShowcase />);
      act(() => void vi.advanceTimersByTime(content.authShowcase.intervalMs * 3));
      expect(current().getAttribute("aria-label")).toContain(slides[0].title);
      expect(screen.queryByRole("button", { name: /pause slideshow/i })).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Next slide" }));
      expect(current().getAttribute("aria-label")).toContain(slides[1].title);
      fireEvent.click(screen.getByRole("button", { name: "Previous slide" }));
      fireEvent.click(screen.getByRole("button", { name: "Previous slide" }));
      expect(current().getAttribute("aria-label")).toContain(slides.at(-1)!.title); // wraps around
      const dot = screen.getByRole("button", { name: new RegExp(`Show slide 3`) });
      fireEvent.click(dot);
      expect(dot.getAttribute("aria-current")).toBe("true");
      expect(current().getAttribute("aria-label")).toContain(slides[2].title);
    } finally {
      vi.useRealTimers();
    }
  });
});
