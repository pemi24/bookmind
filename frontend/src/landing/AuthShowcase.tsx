/** The slideshow beside the sign-in and sign-up forms: BookMind's features, shown as product
 * mockups. Advances on its own, but pauses on hover, on keyboard focus, when paused by the button,
 * and always with reduced motion (WCAG 2.2.2). Slides and timing live in content.ts. */
import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { authShowcase, heroChat } from "./content";
import { ChatMockup, FeatureMockup } from "./mockups/Mockups";
import { useReducedMotion } from "./ui/motion";

export default function AuthShowcase() {
  const slides = authShowcase.slides;
  const reduced = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false); // by the button
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const running = !paused && !hovered && !focused && !reduced;

  useEffect(() => {
    if (!running) return;
    const t = window.setTimeout(() => setIndex((i) => (i + 1) % slides.length), authShowcase.intervalMs);
    return () => window.clearTimeout(t);
  }, [running, index, slides.length]);

  const go = (i: number) => setIndex((i + slides.length) % slides.length);
  const btn =
    "flex h-9 w-9 items-center justify-center rounded-full text-on-panel/90 transition hover:bg-white/15 hover:text-on-panel focus-visible:outline-2 focus-visible:outline-on-panel";

  return (
    <section
      aria-roledescription="carousel"
      aria-label={authShowcase.label}
      className="mx-auto w-full max-w-lg"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setFocused(true)}
      onBlur={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && setFocused(false)}
    >
      {/* all slides share one grid cell, so the panel keeps the height of the tallest */}
      <div className="grid" aria-live={running ? "off" : "polite"}>
        {slides.map((s, i) => {
          const active = i === index;
          return (
            <div
              key={s.title}
              role="group"
              aria-roledescription="slide"
              aria-label={`${i + 1} of ${slides.length}: ${s.title}`}
              aria-hidden={!active}
              className={`col-start-1 row-start-1 flex flex-col justify-end ${reduced ? "" : "transition-[opacity,transform] duration-700 ease-out"} ${
                active ? "opacity-100" : "pointer-events-none translate-y-2 opacity-0"
              }`}
            >
              <div className="pointer-events-none text-left select-none" aria-hidden="true">
                {s.mockup === "chat" ? <ChatMockup chat={heroChat} /> : <FeatureMockup name={s.mockup} />}
              </div>
              <h2 className="mt-8 font-display text-[clamp(1.6rem,2.4vw,2.1rem)] leading-tight font-medium text-on-panel">{s.title}</h2>
              <p className="mt-2 max-w-md text-base leading-relaxed text-on-panel/85">{s.text}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-8 flex items-center gap-1">
        <button onClick={() => go(index - 1)} className={btn} aria-label="Previous slide">
          <ChevronLeft size={18} aria-hidden="true" />
        </button>
        <div className="flex items-center gap-1.5 px-1">
          {slides.map((s, i) => (
            <button
              key={s.title}
              onClick={() => go(i)}
              aria-label={`Show slide ${i + 1}: ${s.title}`}
              aria-current={i === index ? "true" : undefined}
              className="group flex h-6 items-center focus-visible:outline-2 focus-visible:outline-on-panel"
            >
              <span
                className={`block h-1.5 rounded-full transition-all duration-300 ${i === index ? "w-6 bg-on-panel" : "w-1.5 bg-on-panel/40 group-hover:bg-on-panel/70"}`}
              />
            </button>
          ))}
        </div>
        <button onClick={() => go(index + 1)} className={btn} aria-label="Next slide">
          <ChevronRight size={18} aria-hidden="true" />
        </button>
        {!reduced && (
          <button onClick={() => setPaused((p) => !p)} className={`${btn} ml-auto`} aria-label={paused ? "Play slideshow" : "Pause slideshow"}>
            {paused ? <Play size={16} aria-hidden="true" /> : <Pause size={16} aria-hidden="true" />}
          </button>
        )}
      </div>
    </section>
  );
}
